"""Pre-migration assessment: runs without an LLM, so it is instant and free."""

import re

from app.analysis.graph import build_graph
from app.analysis.manifest import import_name
from app.analysis.project import Project
from app.analysis.risks import SEVERITY_WEIGHT, find_risks
from app.analysis.symbols import FileSymbols, extract
from app.mapping.classes import map_classes
from app.mapping.libraries import map_libraries
from app.mapping.types import map_types

MANUAL_LOC_PER_HOUR = 30  # rough industry figure for careful manual porting incl. tests


def looks_like_source(language: str, code: str) -> bool:
    """Cheap sanity check that a file with syntax errors was at least meant to be code."""
    if language == "cpp":
        return ";" in code and "{" in code
    return bool(re.search(r"^\s*(def|class|import|from|for|while|if|print)\b|\w\s*=\s*\S", code, re.M))


STDIN_RE = {
    "cpp": re.compile(r"\b(cin|scanf|getline|getchar|gets|fgets|fread|read)\s*\(|\bcin\b|\bstdin\b|istream_iterator|\bstd::cin\b"),
    "python": re.compile(r"\binput\s*\(|\bstdin\b|fileinput"),
}


def reads_stdin(language: str, files: dict[str, str]) -> bool:
    rx = STDIN_RE[language]
    return any(rx.search(t) for t in files.values())


def _manifest_summary(m: dict) -> dict:
    out: dict = {}
    if "requirements" in m:
        out["requirements"] = m["requirements"]
    if "cmake" in m:
        c = m["cmake"]
        out["cmake"] = {
            "std": c.get("std"),
            "selected_target": c.get("selected_target"),
            "targets": list(c.get("targets", {})),
            "include_dirs": c.get("include_dirs", []),
            "packages": c.get("packages", []),
        }
    return out


def analyze(project: Project) -> tuple[dict, dict]:
    """Returns (assessment, suggested mappings)."""
    symbols: dict[str, FileSymbols] = {p: extract(project.language, p, t) for p, t in project.files.items()}
    graph = build_graph(project, symbols)
    risks = {p: find_risks(project.language, p, t, symbols[p]) for p, t in project.files.items()}
    all_risks = [r for rs in risks.values() for r in rs]
    classes = [c for s in symbols.values() for c in s.classes]

    units = []
    for uid, u in graph.units.items():
        loc = sum(symbols[f].loc for f in u.files)
        cx = sum(symbols[f].complexity for f in u.files)
        rscore = sum(SEVERITY_WEIGHT[r.severity] for f in u.files for r in risks[f])
        ncls = sum(len(symbols[f].classes) for f in u.files)
        difficulty = min(100, round(loc / 4 + cx * 1.2 + rscore * 2.5 + ncls * 4))
        hours = loc / MANUAL_LOC_PER_HOUR * (1 + rscore / 25)
        units.append(
            {
                "id": uid,
                "files": u.files,
                "is_entry": u.is_entry,
                "deps": u.deps,
                "external": u.external,
                "loc": loc,
                "complexity": cx,
                "classes": ncls,
                "functions": sum(len(symbols[f].functions) for f in u.files),
                "risk_score": rscore,
                "difficulty": difficulty,
                "manual_hours": round(hours, 1),
            }
        )

    used: dict[str, list[str]] = {}  # external library -> files importing it
    for u in graph.units.values():
        for ext in u.external:
            files = used.setdefault(ext, [])
            for f in u.files:
                if f not in files and any(i.module == ext or i.module.split(".")[0] == ext for i in symbols[f].imports):
                    files.append(f)
    declared: list[str] = []
    if project.language == "python":
        for pkg in project.manifest.get("requirements", []):
            imp = import_name(pkg)
            if any(imp.lower() == k.split(".")[0].lower() for k in used):
                continue  # already mapped from an actual import
            used[imp] = []
            declared.append(pkg)
    big_ints = any(r.rule == "big-int" for r in all_risks)
    libs = map_libraries(project.language, used, big_ints)
    for lib in libs:
        if lib.source in declared or any(import_name(d) == lib.source for d in declared):
            lib.note = ("declared in requirements.txt but not imported by the code. " + lib.note).strip()
    types = [t.to_dict() for t in map_types(project.language, project.files)]
    if any(r.rule == "dict-order" for r in all_risks):
        for t in types:
            if t["source"] == "dict":
                t["target"] = "insertion-ordered map: Vec<(K, V)> plus HashMap<K, usize> index"
                t["note"] = "Iteration order reaches the output (dict-order risk); a plain HashMap would reorder it."
    mappings = {
        "types": types,
        "libraries": [m.to_dict() for m in libs],
        "classes": [c.to_dict() for c in map_classes(project.language, classes)],
    }

    syntax = {p: s.syntax_errors for p, s in symbols.items() if s.syntax_errors}
    blockers = []
    if syntax:
        blockers.append("Syntax errors: " + ", ".join(f"{p} line {ls[0]}" for p, ls in syntax.items()))
        text_like = [p for p in syntax if not looks_like_source(project.language, project.files[p])]
        if text_like:
            blockers.append(
                f"{', '.join(text_like)} does not look like {'C++' if project.language == 'cpp' else 'Python'} source code. "
                "It may be a program's output or plain text: upload the source file instead."
            )
    elif not any(s.functions or s.classes or s.has_calls for s in symbols.values()):
        blockers.append("No functions or classes found: there is no code to migrate.")
    entries = [u for u in graph.units.values() if u.is_entry]
    if len(entries) > 1:
        blockers.append("More than one entry point: " + ", ".join(u.id for u in entries))
    if not entries and len(graph.units) > 1:
        blockers.append("No entry point (main / __main__ / stdin reader) in a multi-file project")
    unsupported = [m.source for m in libs if m.kind == "unsupported"]

    sev = {s: sum(1 for r in all_risks if r.severity == s) for s in ("high", "medium", "low")}
    total_loc = project.loc
    hours = round(sum(u["manual_hours"] for u in units), 1)
    mapped = sum(1 for m in libs if m.kind in ("std", "crate"))
    if blockers:
        readiness, verdict = "blocked", "Fix the blockers before migrating."
    elif unsupported or sev["high"] >= 3:
        readiness, verdict = "hard", "Migratable, but expect manual work on the flagged constructs."
    elif sev["high"] or sev["medium"] >= 4:
        readiness, verdict = "moderate", "Good candidate; review the flagged constructs in the report."
    else:
        readiness, verdict = "easy", "Straightforward migration."

    assessment = {
        "language": project.language,
        "summary": {
            "files": len(project.files),
            "loc": total_loc,
            "units": len(units),
            "classes": len(classes),
            "functions": sum(len(s.functions) for s in symbols.values()),
            "risks": sev,
            "manual_hours": hours,
            "library_coverage": round(mapped / len(libs), 2) if libs else 1.0,
            "readiness": readiness,
            "verdict": verdict,
            "blockers": blockers,
            "unsupported": unsupported,
            "single_function": len(project.files) == 1 and not entries and not blockers,
            "reads_stdin": reads_stdin(project.language, project.files),
            "manifest": _manifest_summary(project.manifest),
        },
        "graph": graph.to_dict(),
        "units": units,
        "risks": sorted((r.to_dict() for r in all_risks), key=lambda r: (-SEVERITY_WEIGHT[r["severity"]], r["file"], r["line"])),
        "symbols": {p: s.to_dict() for p, s in symbols.items()},
    }
    return assessment, mappings
