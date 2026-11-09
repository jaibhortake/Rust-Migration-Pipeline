"""Benchmark the pipeline against a one-shot LLM baseline and against itself with one feature switched off.

    cd backend && .venv/Scripts/python -m scripts.benchmark [--configs full,baseline,no-contract,...] [--only NAME] [--limit N]

Configurations:
  full          everything on
  baseline      ONE LLM call, whole source in, main.rs out: no analysis, contract, tests-guided repair or compile fixes
  no-contract   translator gets no class/library/type contract and no hazard notes
  no-targeting  no mutation fuzzing and no coverage-targeted test prompts (LLM seed inputs only)
  no-minimize   failing inputs are not shrunk before the repair prompt
  no-repair     no behavioural repair rounds: translate, fix compile errors, compare once
  no-unit       skip the function-level check

Every configuration is scored on its own recorded tests; the baseline is scored on the full run's tests, so it is judged
on the same inputs. Results are cached in SQLite by prompt, so re-runs are cheap. Writes backend/benchmark_results.json.
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
ABLATIONS = {"no-contract": "contract", "no-targeting": "targeting", "no-minimize": "minimize", "no-repair": "repair", "no-unit": "unit"}


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


def summarize(res: dict, seconds: float) -> dict:
    ev = res.get("evidence", {})
    return {
        "status": res["status"],
        "tests_passed": ev.get("tests_passed", 0),
        "tests_total": ev.get("tests_total", 0),
        "line_coverage": ev.get("line_coverage"),
        "branch_coverage": ev.get("branch_coverage"),
        "quality": (res.get("quality") or {}).get("score"),
        "seconds": round(seconds, 1),
        "llm_calls": res.get("usage", {}).get("calls", 0) + res.get("usage", {}).get("cached", 0),
        "repairs": res.get("attempts", {}),
        "contract_followed": (res.get("contract") or {}).get("followed"),
        "contract_total": (res.get("contract") or {}).get("total"),
        "unit": (res.get("unit") or {}).get("status"),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="full,baseline", help="comma list; see the module docstring")
    ap.add_argument("--only", help="substring of the sample name")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = [c for c in configs if c not in ("full", "baseline", *ABLATIONS)]
    if unknown:
        raise SystemExit(f"unknown configs: {unknown}")
    items = [i for i in collect() if not args.only or args.only in i[0]][: args.limit]
    rows = []
    for name, kind, files in items:
        project = build_project(files)
        row: dict = {"name": name, "language": project.language, "kind": kind, "loc": project.loc, "ablations": {}}
        full_res = None
        for cfg in configs:
            if cfg == "baseline":
                continue
            settings.ablate = ABLATIONS.get(cfg, "")
            t0 = time.time()
            res = await run_migration(build_project(files), {}, quiet)
            settings.ablate = ""
            summary = summarize(res, time.time() - t0)
            if cfg == "full":
                row["pipeline"], full_res = summary, res
            else:
                row["ablations"][cfg] = summary
        if "full" not in configs:
            row["pipeline"] = {"status": "skipped", "tests_passed": 0, "tests_total": 0, "seconds": 0, "llm_calls": 0}
        row["baseline"] = {"status": "skipped", "tests_passed": 0, "tests_total": 0}
        if "baseline" in configs and full_res and full_res.get("tests"):
            try:
                row["baseline"] = await baseline(full_res["original_files"], project.language, full_res["tests"])
            except Exception as e:  # a baseline failure must not stop the benchmark
                row["baseline"] = {"status": "failed", "tests_passed": 0, "tests_total": len(full_res["tests"]), "error": str(e)[:200]}
        rows.append(row)
        p, b = row["pipeline"], row["baseline"]
        abl = " ".join(f"{k}={v['status'][:4]}" for k, v in row["ablations"].items())
        print(
            f"{name:<30} full {p['status']:<14} {p['tests_passed']}/{p['tests_total']} cov {p.get('line_coverage')}  "
            f"baseline {b['status']:<12} {abl}",
            flush=True,
        )

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 3) if xs else None

    totals = {
        "programs": len(rows),
        "pipeline_equivalent": sum(r["pipeline"]["status"] == "equivalent" for r in rows),
        "baseline_equivalent": sum(r["baseline"]["status"] == "equivalent" for r in rows),
        "mean_line_coverage": mean(r["pipeline"].get("line_coverage") for r in rows),
        "mean_quality": mean(r["pipeline"].get("quality") for r in rows),
        "mean_llm_calls": mean(r["pipeline"].get("llm_calls") for r in rows),
        "ablations": {
            cfg: {
                "equivalent": sum(r["ablations"].get(cfg, {}).get("status") == "equivalent" for r in rows),
                "mean_line_coverage": mean(r["ablations"].get(cfg, {}).get("line_coverage") for r in rows),
                "mean_quality": mean(r["ablations"].get(cfg, {}).get("quality") for r in rows),
            }
            for cfg in configs
            if cfg in ABLATIONS
        },
    }
    OUT.write_text(
        json.dumps(
            {
                "generated": time.strftime("%Y-%m-%d %H:%M"),
                "model": settings.groq_model,
                "configs": configs,
                "rows": rows,
                "totals": totals,
            },
            indent=1,
        )
    )
    print(json.dumps(totals, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
