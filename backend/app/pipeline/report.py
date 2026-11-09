"""MIGRATION_REPORT.md included in the download."""


def _pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


STATUS_TEXT = {
    "equivalent": "Behaviourally equivalent on all recorded tests",
    "partial": "Compiles; some recorded tests still differ",
    "compile_failed": "Did not compile",
    "failed": "Failed",
}


def report_markdown(name: str, project: dict, res: dict) -> str:
    ev = res.get("evidence", {})
    q = res.get("quality") or {}
    a = (project.get("assessment") or {}).get("summary", {})
    lines = [
        f"# Migration report: {name}",
        "",
        f"**Result:** {STATUS_TEXT.get(res.get('status'), res.get('status'))}  ",
        f"**Confidence:** {res.get('confidence', 'none')}  ",
        f"**Sandbox:** {res.get('sandbox', '?')}, **time:** {res.get('seconds', 0)} s",
        "",
        f"## {(res.get('explanation') or {}).get('title', 'Summary')}",
        (res.get("explanation") or {}).get("detail", ""),
        *[f"- {step}" for step in (res.get("explanation") or {}).get("next_steps", [])],
        "",
        '## What "equivalent" means here',
        "The Rust program produced the same standard output as the original on every recorded input "
        f"({ev.get('tests_passed', 0)}/{ev.get('tests_total', 0)}). This is test-based behavioural evidence, not a "
        "proof of equivalence: behaviour on inputs that were not tested, and on lines the tests never executed, is "
        "unverified. The coverage below says how much of the original those inputs exercised.",
        "",
        "## Evidence",
        f"- Line coverage of the original: {_pct(ev.get('line_coverage'))}",
        f"- Branch coverage of the original: {_pct(ev.get('branch_coverage'))}",
        f"- Inputs by origin: {ev.get('inputs_by_origin', {})}",
        f"- Matches that needed float tolerance (1e-9 relative): {ev.get('numeric_matches', 0)}",
        f"- Non-deterministic inputs dropped: {ev.get('flaky_dropped', 0)}",
    ]
    if ev.get("no_input"):
        lines.append("- The program reads no input, so its behaviour is a single deterministic run (compared once).")
    unc = ev.get("uncovered") or {}
    if unc:
        lines.append(
            "- Never-executed lines (review by hand): " + "; ".join(f"{f}: {', '.join(map(str, ls[:20]))}" for f, ls in unc.items())
        )
    if q:
        lines += [
            "",
            "## Code quality",
            f"- Score: {q.get('score')}/100",
            f"- unsafe blocks: {q.get('unsafe')}, unwrap/expect: {q.get('unwraps')}, clone(): {q.get('clones')}",
            f"- Clippy warnings: {q.get('clippy_warnings')} {q.get('clippy_by_lint', {})}",
            f"- Clippy refinement accepted: {res.get('attempts', {}).get('refine_accepted')}",
        ]
    if a:
        lines += [
            "",
            "## Pre-migration assessment",
            f"- {a.get('files')} files, {a.get('loc')} lines, {a.get('classes')} classes, readiness: {a.get('readiness')}",
            f"- Risks: {a.get('risks')}",
            f"- Manual effort estimate: {a.get('manual_hours')} hours",
        ]
    ct = res.get("contract") or {}
    if ct.get("rows"):
        lines += [
            "",
            f"## Migration contract: followed {ct['followed']}/{ct['total']} decisions",
            "| kind | name | expected | followed | where |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {r['kind']} | {r['name']} | {r['expected']} | {'yes' if r['followed'] else 'NO'} | "
            f"{r.get('where') or r.get('detail') or ''} |"
            for r in ct["rows"]
        ]
    mods = res.get("modules") or []
    if mods:
        lines += ["", "## Modules (in migration order)", "| module | source | rust | status | compile fixes |", "|---|---|---|---|---|"]
        lines += [f"| {m['id']} | {', '.join(m['files'])} | {m['rust']} | {m['status']} | {m['fixes']} |" for m in mods]
    risks = (project.get("assessment") or {}).get("risks", [])
    if risks:
        lines += ["", "## Risks flagged before migration (check these in review)"]
        lines += [f"- [{r['severity']}] {r['file']}:{r['line']} {r['title']}: {r['strategy']}" for r in risks[:40]]
    if res.get("failures"):
        lines += ["", "## Remaining differences"]
        for f in res["failures"]:
            lines += ["```", "input:", f.get("minimized") or f["stdin"], "expected:", f["expected"], "actual:", f["actual"], "```"]
    lines += [
        "",
        "## Regression tests",
        "`tests/cases/*.in|out` hold the recorded inputs and the original's outputs; `cargo test` replays them.",
    ]
    return "\n".join(lines) + "\n"
