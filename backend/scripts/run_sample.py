"""Run one sample file through the pipeline from the command line: run_sample.py <python|cpp> <file>"""
import asyncio
import sys
from pathlib import Path

from app.pipeline.runner import run_job


async def emit(stage: str, status: str, data: dict) -> None:
    print(f"[{stage}] {status} {data if data else ''}", flush=True)


async def main() -> None:
    language, path = sys.argv[1], Path(sys.argv[2])
    res = await run_job(language, path.read_text(encoding="utf-8"), emit)
    print(f"\nstatus={res.status} tests={res.tests_passed}/{res.tests_total} attempts={res.attempts} "
          f"providers={sorted(res.providers)} time={res.seconds}s unsafe={res.unsafe_count}")
    if res.message:
        print("message:", res.message)
    print("\n--- Rust ---\n" + res.rust)


asyncio.run(main())
