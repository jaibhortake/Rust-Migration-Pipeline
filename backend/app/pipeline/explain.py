"""Turns raw pipeline outcomes into things a person can act on, and checks the translation against the contract."""

import re

# (pattern on the status message, title, what happened, what to do)
EXPLANATIONS: list[tuple[str, str, str, list[str]]] = [
    (
        r"does not look like",
        "That file is not source code",
        "The file has syntax errors and looks like plain text or a program's printed output, not code.",
        ["Upload the .cpp / .py source file itself, not what it prints."],
    ),
    (
        r"No functions or classes found",
        "No code to migrate",
        "The file parses, but defines no functions or classes.",
        ["Check that you uploaded the right file."],
    ),
    (
        r"original C\+\+ does not compile",
        "Your C++ does not build in the sandbox",
        "The original program must compile before anything can be compared. The compiler output is shown in the pipeline.",
        [
            "Fix the compiler errors (missing #include, wrong standard).",
            "The sandbox uses GCC 14 with -std=c++20; code that needs MSVC-only extensions will not build.",
        ],
    ),
    (
        r"prints nothing",
        "Nothing to compare",
        "The original program printed nothing on every test input, so a matching Rust program proves nothing.",
        ["Make the program print results to stdout, then migrate again."],
    ),
    (
        r"not deterministic",
        "Output changes between runs",
        "The original gives different output when run twice on the same input (time, randomness, addresses).",
        ["Remove or fix timestamps, random numbers and unordered-container printing, then migrate again."],
    ),
    (
        r"no usable test inputs",
        "Could not produce test inputs",
        "Every generated input was rejected by the original program.",
        ["Add a short comment at the top of the file describing the expected input format."],
    ),
    (
        r"driver",
        "Could not wrap the function in a program",
        "The input is a single function without main; the LLM could not write a faithful stdin/stdout driver for it.",
        ["Add a small main() that reads input and calls the function, then migrate again."],
    ),
    (
        r"LLM unavailable|repair stopped",
        "The language model could not be reached",
        "A call to the hosted model failed after retries (network, rate limit or outage). Everything before that point is kept.",
        ["Check your internet connection and GROQ_API_KEY, then press Run again; cached answers are reused."],
    ),
    (
        r"does not compile",
        "The Rust did not compile",
        "The translation still had compile errors after the allowed number of compiler-guided repairs.",
        [
            "Open the pipeline step to read the compiler errors.",
            "Edit the class/library mappings (for example change a trait to an enum) and run again.",
        ],
    ),
    (
        r"tests match after all repair rounds",
        "Rust compiles but behaves differently",
        "The Rust program differs from the original on some recorded inputs after every repair round.",
        [
            "See 'Remaining differences' for the smallest failing input.",
            "Check the risks flagged for those lines in the assessment (integer division, ordering, overflow).",
        ],
    ),
    (
        r"function-level",
        "Some functions behave differently when called directly",
        "The whole program matches, but calling individual functions with generated arguments exposed a difference.",
        ["See the unit-level section of the report for the failing call."],
    ),
    (
        r"internal error",
        "Unexpected error in the migrator",
        "Something went wrong inside the tool, not in your code.",
        ["Run again; if it repeats, check the server log."],
    ),
]

GOOD = {
    "equivalent": (
        "Behaviour matches on every recorded test",
        "The Rust program printed exactly what the original printed on all recorded inputs. Coverage and confidence below say "
        "how much of the original those inputs exercised. This is test evidence, not a proof.",
    ),
}


def explain(result: dict) -> dict:
    status = result.get("status", "failed")
    msg = result.get("message", "") or ""
    if status == "equivalent":
        title, detail = GOOD["equivalent"]
        steps = []
        unit = result.get("unit") or {}
        if unit.get("status") == "partial":
            steps.append(
                f"Function-level check: {unit['tests_total'] - unit['tests_passed']} of {unit['tests_total']} direct-call sequences "
                "differ (see that section); confidence is capped at medium."
            )
        if result.get("confidence") in ("low", "medium"):
            steps.append("Some lines were never executed by any test: review them by hand (listed in the report).")
        return {"title": title, "detail": detail, "next_steps": steps}
    for pat, title, detail, steps in EXPLANATIONS:
        if re.search(pat, msg, re.I):
            return {"title": title, "detail": detail, "next_steps": steps}
    if status == "partial":
        return {
            "title": "Partly verified",
            "detail": "Some recorded tests still differ from the original.",
            "next_steps": ["See 'Remaining differences'."],
        }
    return {"title": "The migration did not finish", "detail": msg or "No details were recorded.", "next_steps": ["Run again."]}


def _any(pattern: str, rust: dict[str, str]) -> str | None:
    rx = re.compile(pattern)
    for path, code in rust.items():
        m = rx.search(code)
        if m:
            return f"{path}:{code[: m.start()].count(chr(10)) + 1}"
    return None


def contract_adherence(mappings: dict, rust: dict[str, str]) -> dict:
    """For every class and library decision in the contract: did the generated Rust follow it?"""
    rows: list[dict] = []
    for c in mappings.get("classes", []):
        n = re.escape(c["name"])
        strategy = c["strategy"]
        if strategy == "trait":
            expected, pattern = f"trait {c['name']}", rf"\btrait\s+{n}\b"
        elif strategy == "enum":
            expected, pattern = f"enum {c['name']}", rf"\benum\s+{n}\b"
        elif strategy == "error":
            expected, pattern = f"error type {c['name']}", rf"\b(enum|struct)\s+{n}\b"
        elif strategy == "implementor":
            expected, pattern = f"struct {c['name']} + impl … for {c['name']}", rf"\bimpl(<[^>]*>)?\s+[\w:<>, ]+\s+for\s+{n}\b"
        else:
            expected, pattern = f"struct {c['name']}", rf"\b(struct|enum)\s+{n}\b"
        where = _any(pattern, rust)
        extra = ""
        if strategy == "implementor" and not where and _any(rf"\b(struct|enum)\s+{n}\b", rust):
            extra = "defined, but without a trait impl"
        rows.append(
            {
                "kind": "class",
                "name": c["name"],
                "strategy": strategy,
                "expected": expected,
                "followed": where is not None,
                "where": where,
                "detail": extra or ("" if where else "not found in the generated code"),
            }
        )
    for lib in mappings.get("libraries", []):
        if lib.get("kind") == "crate":
            for crate in lib.get("crates", []):
                ident = crate.replace("-", "_")
                where = _any(rf"\b{ident}::", rust) or _any(rf"\buse\s+{ident}\b", rust)
                rows.append(
                    {
                        "kind": "library",
                        "name": lib["source"],
                        "strategy": "crate",
                        "expected": f"uses crate {crate}",
                        "followed": where is not None,
                        "where": where,
                        "detail": "" if where else "crate declared but never used (the model may have used the standard library)",
                    }
                )
        elif lib.get("kind") == "unsupported":
            rows.append(
                {
                    "kind": "library",
                    "name": lib["source"],
                    "strategy": "unsupported",
                    "expected": "flagged as unsupported",
                    "followed": True,
                    "where": None,
                    "detail": "needs a manual decision",
                }
            )
    followed = sum(1 for r in rows if r["followed"])
    return {"rows": rows, "followed": followed, "total": len(rows)}
