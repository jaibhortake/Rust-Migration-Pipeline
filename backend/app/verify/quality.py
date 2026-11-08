"""Idiom and safety scoring of the generated Rust."""

import json
import re
from collections import Counter

# Lints that indicate unidiomatic or risky code weigh more than style nits.
HEAVY = {
    "clippy::needless_range_loop": 2,
    "clippy::ptr_arg": 2,
    "clippy::unwrap_used": 1,
    "clippy::clone_on_copy": 1,
    "clippy::redundant_clone": 2,
    "clippy::manual_memcpy": 2,
    "clippy::too_many_arguments": 1,
    "clippy::cast_possible_truncation": 1,
}


def parse_clippy(stdout: str) -> list[dict]:
    """cargo clippy --message-format=json output -> warnings in our own sources."""
    out = []
    for line in stdout.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("reason") != "compiler-message":
            continue
        m = msg.get("message", {})
        if m.get("level") not in ("warning", "error"):
            continue
        code = (m.get("code") or {}).get("code") or ""
        spans = [s for s in m.get("spans", []) if s.get("is_primary")]
        if not spans or not code:
            continue
        out.append(
            {"lint": code, "message": m.get("message", ""), "file": spans[0].get("file_name", ""), "line": spans[0].get("line_start", 0)}
        )
    return out


def _strip(rust: str) -> str:
    rust = re.sub(r"//[^\n]*", "", rust)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', rust)


def score(files: dict[str, str], warnings: list[dict], fmt_changed_lines: int | None) -> dict:
    code = _strip("\n".join(files.values()))
    loc = max(1, len([ln for ln in code.splitlines() if ln.strip()]))
    per100 = 100 / loc
    unsafe = len(re.findall(r"\bunsafe\b", code))
    unwraps = len(re.findall(r"\.unwrap\(\)|\.expect\(", code))
    clones = len(re.findall(r"\.clone\(\)", code))
    refcell = len(re.findall(r"\bRefCell\b|\bRc<", code))
    by_lint = Counter(w["lint"] for w in warnings)
    lint_penalty = sum(HEAVY.get(k, 1) * v for k, v in by_lint.items())

    s = 100.0
    s -= min(30, unsafe * 15)
    s -= min(25, lint_penalty * 2.5)
    s -= min(15, unwraps * per100 * 2)  # unwrap on stdin parsing is normal; only density matters
    s -= min(10, clones * per100 * 2)
    s -= min(10, refcell * per100 * 3)
    if fmt_changed_lines:
        s -= min(10, fmt_changed_lines * per100)
    return {
        "score": max(0, round(s)),
        "loc": loc,
        "unsafe": unsafe,
        "unwraps": unwraps,
        "clones": clones,
        "shared_mutability": refcell,
        "clippy_warnings": len(warnings),
        "clippy_by_lint": dict(by_lint.most_common()),
        "rustfmt_changed_lines": fmt_changed_lines,
        "warnings": warnings[:30],
    }
