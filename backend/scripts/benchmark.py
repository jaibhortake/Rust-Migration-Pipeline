"""Benchmark the pipeline over samples/python and samples/cpp.

Run from E:\\kaggle\\migration with PYTHONPATH=backend:
    python backend/scripts/benchmark.py [--only SUBSTR] [--language python|cpp]
NOTE: this calls LLM providers (paid/limited).
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from app.pipeline.runner import run_job

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
OUT = ROOT / "backend" / "benchmark_results.json"
EXTS = {"python": ".py", "cpp": ".cpp"}


async def emit(stage: str, status: str, data: dict) -> None:
    pass


def collect(language: str | None, only: str | None) -> list[tuple[str, Path]]:
    items = []
    for lang, ext in EXTS.items():
        if language and lang != language:
            continue
        for p in sorted((SAMPLES / lang).glob(f"*{ext}")):
            if only and only not in p.name:
                continue
            items.append((lang, p))
    return items


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="only files whose name contains this substring")
    ap.add_argument("--language", choices=list(EXTS), help="limit to one language")
    args = ap.parse_args()

    items = collect(args.language, args.only)
    if not items:
        print("no matching sample files")
        return

    rows = []
    header = f"{'file':<32}{'status':<12}{'tests':<8}{'attempts':<10}{'providers':<24}{'seconds':>8}"
    print(header)
    print("-" * len(header))
    for lang, path in items:
        name = f"{lang}/{path.name}"
        t0 = time.time()
        try:
            res = await run_job(lang, path.read_text(encoding="utf-8"), emit)
            row = {
                "file": name, "status": res.status, "tests_passed": res.tests_passed,
                "tests_total": res.tests_total, "attempts": res.attempts,
                "providers": sorted(res.providers), "seconds": res.seconds,
                "unsafe_count": res.unsafe_count, "message": res.message,
            }
        except Exception as e:  # keep going on a per-file crash
            row = {
                "file": name, "status": "error", "tests_passed": 0, "tests_total": 0,
                "attempts": 0, "providers": [], "seconds": round(time.time() - t0, 2),
                "unsafe_count": 0, "message": f"{type(e).__name__}: {e}",
            }
        rows.append(row)
        print(f"{name:<32}{row['status']:<12}{row['tests_passed']}/{row['tests_total']:<6}"
              f"{row['attempts']:<10}{','.join(row['providers']):<24}{row['seconds']:>8}", flush=True)

    verified = sum(1 for r in rows if r["status"] == "verified")
    pct = 100.0 * verified / len(rows)
    print(f"\nverified {verified}/{len(rows)} ({pct:.1f}%)")
    OUT.write_text(json.dumps({"verified": verified, "total": len(rows), "percent_verified": pct,
                               "results": rows}, indent=2), encoding="utf-8")
    print(f"results written to {OUT}")


asyncio.run(main())
