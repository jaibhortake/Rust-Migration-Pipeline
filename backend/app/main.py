import asyncio
import io
import json
import logging
import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from app import db
from app.analysis.assess import analyze
from app.analysis.project import Project, ProjectError, build_project, files_from_zip
from app.config import ROOT, config_problems, settings
from app.mapping.classes import STRATEGIES
from app.pipeline.report import report_markdown
from app.pipeline.runner import WORKSPACE, run_migration
from app.sandbox import remove_orphans, sandbox_status
from app.security import (
    COOKIE,
    check_password,
    issue_token,
    login_limiter,
    require_user,
    token_user,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("migrator")

problems = config_problems()
if problems:
    raise SystemExit("Refusing to start: " + "; ".join(problems) + " (see .env.example)")

app = FastAPI(title="Rust Migration Pipeline")
db.connect()
db.mark_interrupted()


class LiveJob:
    def __init__(self, jid: str, project_id: str):
        self.id, self.project_id = jid, project_id
        self.events: list[dict] = []
        self.subscribers: list[asyncio.Queue] = []
        self.done = False

    async def emit(self, stage: str, status: str, data: dict) -> None:
        ev = {"stage": stage, "status": status, **data}
        self.events.append(ev)
        for q in self.subscribers:
            q.put_nowait(ev)


LIVE: dict[str, LiveJob] = {}


@app.on_event("startup")
async def _cleanup() -> None:
    """Containers and job folders left by a server that was killed mid-job."""
    await remove_orphans()
    if WORKSPACE.exists():
        for d in WORKSPACE.iterdir():
            shutil.rmtree(d, ignore_errors=True)


TASKS: set[asyncio.Task] = set()


# ------------------------------------------------------------------ auth


class Login(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=500)


@app.post("/api/login")
async def login(body: Login, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not login_limiter.allow(ip):
        raise HTTPException(429, "too many login attempts, wait a minute")
    if not check_password(body.username, body.password):
        raise HTTPException(401, "invalid credentials")
    response.set_cookie(
        COOKIE,
        issue_token(body.username),
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.session_max_age_s,
    )
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
async def me(user: str = Depends(require_user)):
    return {"user": user}


@app.get("/api/health")
async def health():
    return {"ok": True, "llm": "groq" if settings.groq_api_key else "ollama", "sandbox": await sandbox_status()}


# ------------------------------------------------------------------ projects


class Paste(BaseModel):
    name: str = Field(default="", max_length=120)
    language: str = Field(pattern="^(cpp|python)$")
    files: dict[str, str] = Field(min_length=1)


def _create(name: str, project: Project) -> dict:
    assessment, mappings = analyze(project)
    pid = uuid.uuid4().hex[:12]
    name = name.strip() or next(iter(project.files)).rsplit("/", 1)[-1]
    db.insert_project(pid, name, project.language, project.files, assessment, mappings)
    return {"id": pid}


@app.post("/api/projects", dependencies=[Depends(require_user)])
async def create_project(body: Paste):
    try:
        project = build_project(body.files, body.language)
    except ProjectError as e:
        raise HTTPException(422, str(e)) from e
    return await asyncio.to_thread(_create, body.name, project)


@app.post("/api/projects/upload", dependencies=[Depends(require_user)])
async def upload_project(files: list[UploadFile] = File(...), name: str = Form("")):
    collected: dict[str, str] = {}
    total = 0
    for f in files[: settings.max_files + 1]:
        data = await f.read(settings.max_upload_bytes + 1)
        total += len(data)
        if total > settings.max_upload_bytes:
            raise HTTPException(413, "upload is too large")
        try:
            if (f.filename or "").lower().endswith(".zip"):
                collected.update(files_from_zip(data))
            else:
                collected[f.filename or "main"] = data.decode("utf-8", errors="replace")
        except ProjectError as e:
            raise HTTPException(422, str(e)) from e
    try:
        project = build_project(collected)
    except ProjectError as e:
        raise HTTPException(422, str(e)) from e
    return await asyncio.to_thread(_create, name, project)


@app.get("/api/projects", dependencies=[Depends(require_user)])
async def list_projects():
    rows = await asyncio.to_thread(db.list_projects)
    for r in rows:
        if any(j.project_id == r["id"] and not j.done for j in LIVE.values()):
            r["status"] = "running"
    return rows


def _project_or_404(pid: str) -> dict:
    p = db.get_project(pid)
    if not p:
        raise HTTPException(404, "no such project")
    return p


@app.get("/api/projects/{pid}", dependencies=[Depends(require_user)])
async def get_project(pid: str):
    p = await asyncio.to_thread(_project_or_404, pid)
    p["jobs"] = await asyncio.to_thread(db.project_jobs, pid)
    p["strategies"] = STRATEGIES
    return p


@app.delete("/api/projects/{pid}", dependencies=[Depends(require_user)])
async def delete_project(pid: str):
    if any(j.project_id == pid and not j.done for j in LIVE.values()):
        raise HTTPException(409, "a migration of this project is running")
    await asyncio.to_thread(db.delete_project, pid)
    return {"ok": True}


class Mappings(BaseModel):
    types: list[dict] = Field(max_length=200)
    libraries: list[dict] = Field(max_length=200)
    classes: list[dict] = Field(max_length=500)


@app.put("/api/projects/{pid}/mappings", dependencies=[Depends(require_user)])
async def save_mappings(pid: str, body: Mappings):
    await asyncio.to_thread(_project_or_404, pid)
    for c in body.classes:
        if c.get("strategy") not in STRATEGIES:
            raise HTTPException(422, f"unknown strategy for {c.get('name')}")
    if len(json.dumps(body.model_dump())) > 500_000:
        raise HTTPException(413, "mappings too large")
    await asyncio.to_thread(db.update_mappings, pid, body.model_dump())
    return {"ok": True}


@app.post("/api/projects/{pid}/reset-mappings", dependencies=[Depends(require_user)])
async def reset_mappings(pid: str):
    p = await asyncio.to_thread(_project_or_404, pid)
    _, mappings = analyze(Project(p["language"], p["files"]))
    await asyncio.to_thread(db.update_mappings, pid, mappings)
    return mappings


@app.post("/api/projects/{pid}/migrate", dependencies=[Depends(require_user)])
async def migrate(pid: str):
    p = await asyncio.to_thread(_project_or_404, pid)
    if any(j.project_id == pid and not j.done for j in LIVE.values()):
        raise HTTPException(409, "a migration of this project is already running")
    if p["assessment"]["summary"]["blockers"] and not p["assessment"]["summary"]["single_function"]:
        raise HTTPException(422, "fix the blockers shown in the assessment first")
    jid = uuid.uuid4().hex[:12]
    job = LiveJob(jid, pid)
    LIVE[jid] = job
    await asyncio.to_thread(db.save_job, jid, pid, "running", [], None)

    async def work() -> None:
        try:
            result = await run_migration(Project(p["language"], p["files"]), p["mappings"], job.emit)
            status = result["status"]
        except Exception as e:  # never leave a job "running"
            log.exception("job %s crashed", jid)
            result, status = {"status": "failed", "message": f"internal error: {e}"}, "failed"
            await job.emit("done", "failed", {"message": result["message"]})
        await asyncio.to_thread(db.save_job, jid, pid, status, job.events, result)
        job.done = True
        log.info("job %s finished: %s", jid, status)

    task = asyncio.create_task(work())
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {"id": jid}


# ------------------------------------------------------------------ jobs


@app.get("/api/jobs/{jid}", dependencies=[Depends(require_user)])
async def get_job(jid: str):
    live = LIVE.get(jid)
    if live and not live.done:
        return {"id": jid, "project_id": live.project_id, "status": "running", "events": live.events, "result": None}
    j = await asyncio.to_thread(db.get_job, jid)
    if not j:
        raise HTTPException(404, "no such job")
    return j


@app.get("/api/jobs/{jid}/download", dependencies=[Depends(require_user)])
async def download(jid: str):
    j = await asyncio.to_thread(db.get_job, jid)
    if not j or not j["result"] or not j["result"].get("files"):
        raise HTTPException(404, "no result to download")
    p = await asyncio.to_thread(db.get_project, j["project_id"])
    res = j["result"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, text in res["files"].items():
            z.writestr(f"migrated/{path}", text)
        for path, text in res.get("original_files", {}).items():
            z.writestr(f"migrated/original/{path}", text)
        # the differential tests become a regression suite: `cargo test` replays them against the binary
        for i, c in enumerate(res.get("tests", [])):
            z.writestr(f"migrated/tests/cases/{i:03}.in", c["stdin"])
            z.writestr(f"migrated/tests/cases/{i:03}.out", c["expected"])
        if res.get("tests"):
            z.writestr("migrated/tests/golden.rs", GOLDEN_RS)
        z.writestr("migrated/MIGRATION_REPORT.md", report_markdown(p["name"] if p else jid, p or {}, res))
    return Response(
        buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="migrated-{jid}.zip"'}
    )


GOLDEN_RS = r"""//! Golden tests recorded from the ORIGINAL program during migration.
use std::io::Write;
use std::process::{Command, Stdio};

fn norm(s: &str) -> String {
    s.trim().lines().map(|l| l.trim_end()).collect::<Vec<_>>().join("\n")
}

#[test]
fn matches_original_outputs() {
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/cases");
    let mut inputs: Vec<_> = std::fs::read_dir(&dir).unwrap().filter_map(|e| e.ok()).map(|e| e.path())
        .filter(|p| p.extension().map_or(false, |x| x == "in")).collect();
    inputs.sort();
    let mut failed = Vec::new();
    for input in &inputs {
        let stdin = std::fs::read_to_string(input).unwrap();
        let expected = std::fs::read_to_string(input.with_extension("out")).unwrap();
        let mut child = Command::new(env!("CARGO_BIN_EXE_migrated"))
            .stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap();
        child.stdin.take().unwrap().write_all(stdin.as_bytes()).unwrap();
        let out = child.wait_with_output().unwrap();
        if norm(&String::from_utf8_lossy(&out.stdout)) != norm(&expected) {
            failed.push(input.display().to_string());
        }
    }
    assert!(failed.is_empty(), "outputs differ for: {:?}", failed);
}
"""


@app.websocket("/api/jobs/{jid}/ws")
async def job_ws(ws: WebSocket, jid: str):
    if not token_user(ws.cookies.get(COOKIE)):
        await ws.close(code=4401)
        return
    job = LIVE.get(jid)
    await ws.accept()
    if job is None:  # finished in a previous server run: replay from the database
        j = await asyncio.to_thread(db.get_job, jid)
        for ev in (j or {}).get("events", []):
            await ws.send_json(ev)
        await ws.close()
        return
    q: asyncio.Queue = asyncio.Queue()
    for ev in job.events:
        q.put_nowait(ev)
    job.subscribers.append(q)
    try:
        while True:
            ev = await q.get()
            await ws.send_json(ev)
            if ev["stage"] == "done":
                break
    except WebSocketDisconnect:
        pass
    finally:
        job.subscribers.remove(q)
        try:
            await ws.close()
        except RuntimeError:
            pass


@app.get("/api/benchmark", dependencies=[Depends(require_user)])
async def benchmark():
    path = ROOT / "backend" / "benchmark_results.json"
    if not path.exists():
        return {"available": False}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@app.get("/api/examples", dependencies=[Depends(require_user)])
async def examples():
    """Sample projects shipped in samples/ (single files and multi-file projects)."""
    out = []
    base = ROOT / "samples"
    for lang, ext in (("python", ".py"), ("cpp", ".cpp")):
        for f in sorted((base / lang).glob(f"*{ext}")):
            out.append(
                {"name": f.stem.replace("_", " "), "language": lang, "kind": "file", "files": {f.name: f.read_text(encoding="utf-8")}}
            )
    for d in sorted((base / "projects").glob("*")) if (base / "projects").exists() else []:
        files = {
            str(p.relative_to(d)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in sorted(d.rglob("*"))
            if p.is_file() and p.suffix in (".py", ".cpp", ".h", ".hpp")
        }
        lang = "python" if any(k.endswith(".py") for k in files) else "cpp"
        out.append({"name": d.name.replace("_", " "), "language": lang, "kind": "project", "files": files})
    return out


# ------------------------------------------------------------------ production: serve the built frontend

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and Path(DIST.resolve()) in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
