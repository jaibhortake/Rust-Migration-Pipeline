import asyncio
import hmac
import io
import json
import logging
import uuid
import zipfile
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field

from app import db
from app.config import ROOT, settings
from app.pipeline.runner import CARGO_TOML, run_job

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Rust Migration Pipeline")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5280", "http://127.0.0.1:5280"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

signer = URLSafeSerializer(settings.session_secret, salt="session")
COOKIE = "session"
MAX_CODE_CHARS = 50_000


class Job:
    def __init__(self, language: str, code: str, job_id: str | None = None):
        self.id = job_id or uuid.uuid4().hex[:12]
        self.language, self.code = language, code
        self.events: list[dict] = []
        self.result: dict | None = None  # JSON-ready result; None while running
        self.subscribers: list[asyncio.Queue] = []

    async def emit(self, stage: str, status: str, data: dict) -> None:
        ev = {"stage": stage, "status": status, **data}
        self.events.append(ev)
        for q in self.subscribers:
            q.put_nowait(ev)


JOBS: dict[str, Job] = {}

for _row in db.load_jobs():  # restore history from previous runs
    _job = Job(_row["language"], _row["code"], _row["id"])
    _job.events, _job.result = _row["events"], _row["result"]
    JOBS[_job.id] = _job


def _authed(token: str | None) -> bool:
    if not token:
        return False
    try:
        return signer.loads(token) == settings.admin_username
    except BadSignature:
        return False


def require_user(request: Request) -> None:
    if not _authed(request.cookies.get(COOKIE)):
        raise HTTPException(401, "not logged in")


class Login(BaseModel):
    username: str
    password: str


class Submit(BaseModel):
    language: str = Field(pattern="^(cpp|python)$")
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)


@app.get("/api/health")
async def health():
    return {"ok": True, "groq": bool(settings.groq_api_key)}


@app.post("/api/login")
async def login(body: Login, response: Response):
    ok = hmac.compare_digest(body.username, settings.admin_username) and hmac.compare_digest(
        body.password, settings.admin_password
    )
    if not ok or not settings.admin_password:
        raise HTTPException(401, "invalid credentials")
    response.set_cookie(COOKIE, signer.dumps(body.username), httponly=True, samesite="lax")
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me", dependencies=[Depends(require_user)])
async def me():
    return {"user": settings.admin_username}


@app.post("/api/jobs", dependencies=[Depends(require_user)])
async def submit(body: Submit):
    job = Job(body.language, body.code)
    JOBS[job.id] = job

    async def work() -> None:
        res = await run_job(job.language, job.code, job.emit)
        data = asdict(res)
        data["providers"] = sorted(data["providers"])
        job.result = data
        await asyncio.to_thread(db.save_job, job.id, job.language, job.code, job.events, res)

    asyncio.create_task(work())
    return {"id": job.id}


@app.get("/api/jobs", dependencies=[Depends(require_user)])
async def list_jobs():
    return [
        {"id": j.id, "language": j.language, "status": j.result["status"] if j.result else "running"}
        for j in reversed(JOBS.values())
    ]


@app.get("/api/jobs/{job_id}", dependencies=[Depends(require_user)])
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {"id": job.id, "language": job.language, "events": job.events, "result": job.result}


@app.get("/api/jobs/{job_id}/download", dependencies=[Depends(require_user)])
async def download(job_id: str):
    job = JOBS.get(job_id)
    if not job or not job.result or not job.result["rust"]:
        raise HTTPException(404, "no result to download")
    ext = "cpp" if job.language == "cpp" else "py"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("migrated/Cargo.toml", CARGO_TOML)
        z.writestr("migrated/src/main.rs", job.result["rust"])
        z.writestr(f"migrated/original.{ext}", job.result["original"])
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="migrated-{job.id}.zip"'},
    )


@app.get("/api/benchmark", dependencies=[Depends(require_user)])
async def benchmark():
    path = ROOT / "backend" / "benchmark_results.json"
    if not path.exists():
        return {"available": False}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@app.websocket("/api/jobs/{job_id}/ws")
async def job_ws(ws: WebSocket, job_id: str):
    if not _authed(ws.cookies.get(COOKIE)):
        await ws.close(code=4401)
        return
    job = JOBS.get(job_id)
    if not job:
        await ws.close(code=4404)
        return
    await ws.accept()
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
        await ws.close()
