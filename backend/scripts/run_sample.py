"""Run the full pipeline on one sample file or project directory and print the event stream and summary.

cd backend && .venv/Scripts/python -m scripts.run_sample ../samples/projects/py_bank
"""

import asyncio
import json
import sys
from pathlib import Path

from app.analysis.project import build_project
from app.pipeline.runner import run_migration


async def emit(stage: str, status: str, data: dict) -> None:
    extra = {k: v for k, v in data.items() if k != "errors"}
    print(f"[{stage:>14}] {status:<8} {json.dumps(extra)[:160]}")
    if data.get("errors"):
        print("    " + str(data["errors"])[-600:].replace("\n", "\n    "))


async def main(target: str) -> None:
    p = Path(target)
    files = (
        {str(f.relative_to(p)).replace("\\", "/"): f.read_text(encoding="utf-8") for f in p.rglob("*") if f.is_file()}
        if p.is_dir()
        else {p.name: p.read_text(encoding="utf-8")}
    )
    res = await run_migration(build_project(files), {}, emit)
    print(json.dumps({k: res.get(k) for k in ("status", "confidence", "message", "evidence", "attempts", "usage", "seconds")}, indent=1))
    print("quality:", json.dumps({k: v for k, v in (res.get("quality") or {}).items() if k != "warnings"}))
    for path, code in res.get("files", {}).items():
        print(f"----- {path}\n{code[:1500]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
