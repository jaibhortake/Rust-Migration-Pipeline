"""Benchmark: full pipeline vs a one-shot LLM baseline on every sample (single files and multi-file projects).

Both are scored on the SAME inputs, recorded from the original program by the pipeline's test generation.
The baseline is what "just ask an LLM" gives you: one call, whole source in, main.rs out, no analysis, no repair.

    cd backend && .venv/Scripts/python -m scripts.benchmark [--only NAME] [--limit N]
Calls the LLM (cached in SQLite, so re-runs are cheap).
"""

import argparse
import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path

from app.analysis.project import build_project
from app.config import ROOT, settings
from app.llm.client import chat
from app.pipeline import prompts
from app.pipeline.runner import WORKSPACE, cargo_toml, compare, extract_block, run_migration
from app.sandbox import make_sandbox

SAMPLES = ROOT / "samples"
OUT = ROOT / "backend" / "benchmark_results.json"


def collect() -> list[tuple[str, str, dict[str, str]]]:
    items = []
    for lang, ext in (("python", ".py"), ("cpp", ".cpp")):
        for p in sorted((SAMPLES / lang).glob(f"*{ext}")):
            items.append((f"{p.stem} ({lang})", "file", {p.name: p.read_text(encoding="utf-8")}))
    for d in sorted((SAMPLES / "projects").iterdir()):
        files = {str(f.relative_to(d)).replace("\\", "/"): f.read_text(encoding="utf-8") for f in sorted(d.rglob("*")) if f.is_file()}
        items.append((d.name, "project", files))
    return items


async def baseline(files: dict[str, str], language: str, tests: list[dict]) -> dict:
    src = "\n\n".join(f"// ===== {p}\n{t}" for p, t in files.items())
    text = await chat(
        [{"role": "system", "content": prompts.BASELINE_SYSTEM}, {"role": "user", "content": f"Language: {language}\n\n{src}"}]
    )
    WORKSPACE.mkdir(exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=WORKSPACE))
    sb = make_sandbox(d)
    out = {"status": "compile_failed", "tests_passed": 0, "tests_total": len(tests)}
    try:
        (d / "rust" / "src").mkdir(parents=True)
        (d / "rust" / "Cargo.toml").write_text(cargo_toml([]))
        (d / "rust" / "src" / "main.rs").write_text(extract_block(text))
        await sb.start()
        cmd = ["cargo", "build", "--release", "--quiet"] + (["--offline"] if sb.name == "docker" else [])
        if not (await sb.run(cmd, "rust", timeout=settings.build_timeout_s)).ok:
            return out
        passed = 0
        for t in tests:
            r = await sb.run([sb.rust_exe()], "rust", t["stdin"])
            passed += r.ok and compare(t["expected"], r.stdout) != "diff"
        out.update(tests_passed=passed, status="equivalent" if passed == len(tests) else "partial")
        return out
    finally:
        await sb.stop()
        shutil.rmtree(d, ignore_errors=True)


async def quiet(*_a) -> None:
    pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="substring of the sample name")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    items = [i for i in collect() if not args.only or args.only in i[0]][: args.limit]
    rows = []
    for name, kind, files in items:
        project = build_project(files)
        t0 = time.time()
        res = await run_migration(project, {}, quiet)
        ev = res.get("evidence", {})
        row = {
            "name": name,
            "language": project.language,
            "kind": kind,
            "loc": project.loc,
            "pipeline": {
                "status": res["status"],
                "tests_passed": ev.get("tests_passed", 0),
                "tests_total": ev.get("tests_total", 0),
                "line_coverage": ev.get("line_coverage"),
                "branch_coverage": ev.get("branch_coverage"),
                "quality": (res.get("quality") or {}).get("score"),
                "seconds": round(time.time() - t0, 1),
                "llm_calls": res.get("usage", {}).get("calls", 0) + res.get("usage", {}).get("cached", 0),
                "repairs": res.get("attempts", {}),
            },
            "baseline": {"status": "skipped", "tests_passed": 0, "tests_total": 0},
        }
        if res.get("tests"):
            try:
                row["baseline"] = await baseline(res["original_files"], project.language, res["tests"])
            except Exception as e:  # baseline failures must not stop the benchmark
                row["baseline"] = {"status": "failed", "tests_passed": 0, "tests_total": len(res["tests"]), "error": str(e)[:200]}
        rows.append(row)
        p, b = row["pipeline"], row["baseline"]
        print(
            f"{name:<34} pipeline {p['status']:<14} {p['tests_passed']}/{p['tests_total']} cov {p['line_coverage']}  "
            f"baseline {b['status']:<14} {b['tests_passed']}/{b['tests_total']}  {p['seconds']}s",
            flush=True,
        )

    covs = [r["pipeline"]["line_coverage"] for r in rows if r["pipeline"]["line_coverage"] is not None]
    quals = [r["pipeline"]["quality"] for r in rows if r["pipeline"]["quality"] is not None]
    totals = {
        "pipeline_equivalent": sum(r["pipeline"]["status"] == "equivalent" for r in rows),
        "baseline_equivalent": sum(r["baseline"]["status"] == "equivalent" for r in rows),
        "mean_line_coverage": round(sum(covs) / len(covs), 3) if covs else None,
        "mean_quality": round(sum(quals) / len(quals), 1) if quals else None,
    }
    OUT.write_text(
        json.dumps({"generated": time.strftime("%Y-%m-%d %H:%M"), "model": settings.groq_model, "rows": rows, "totals": totals}, indent=1)
    )
    print(json.dumps(totals))


if __name__ == "__main__":
    asyncio.run(main())
