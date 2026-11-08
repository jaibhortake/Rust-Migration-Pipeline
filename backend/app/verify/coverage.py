"""Line and branch coverage of the ORIGINAL program for a single run, read from gcov / coverage.py JSON."""

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Coverage:
    lines: set[tuple[str, int]] = field(default_factory=set)  # executed (file, line)
    all_lines: set[tuple[str, int]] = field(default_factory=set)  # executable (file, line)
    branches: set[tuple[str, int, int]] = field(default_factory=set)  # taken branch arcs
    all_branches: set[tuple[str, int, int]] = field(default_factory=set)

    def merge(self, other: "Coverage") -> None:
        self.lines |= other.lines
        self.all_lines |= other.all_lines
        self.branches |= other.branches
        self.all_branches |= other.all_branches

    def adds_to(self, total: "Coverage") -> bool:
        return bool(self.lines - total.lines or self.branches - total.branches)

    @property
    def line_rate(self) -> float:
        return len(self.lines) / len(self.all_lines) if self.all_lines else 1.0

    @property
    def branch_rate(self) -> float | None:
        return len(self.branches) / len(self.all_branches) if self.all_branches else None

    def uncovered(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for f, ln in sorted(self.all_lines - self.lines):
            out.setdefault(f, []).append(ln)
        return out


def parse_gcov_dir(obj_dir: Path, project_files: set[str]) -> Coverage:
    """Reads every *.gcov.json.gz produced by `gcov -b --json-format` in obj_dir."""
    cov = Coverage()
    for gz in obj_dir.glob("*.gcov.json.gz"):
        try:
            data = json.loads(gzip.decompress(gz.read_bytes()))
        except (OSError, ValueError):
            continue
        for f in data.get("files", []):
            name = _match(f.get("file", ""), project_files)
            if name is None:
                continue  # system headers
            for ln in f.get("lines", []):
                key = (name, ln["line_number"])
                cov.all_lines.add(key)
                if ln.get("count", 0) > 0:
                    cov.lines.add(key)
                real = [b for b in ln.get("branches", []) if not b.get("throw")]
                for i, b in enumerate(real):
                    bk = (name, ln["line_number"], i)
                    cov.all_branches.add(bk)
                    if b.get("count", 0) > 0:
                        cov.branches.add(bk)
    return cov


def parse_coveragepy(json_path: Path, project_files: set[str]) -> Coverage:
    cov = Coverage()
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cov
    for fname, f in data.get("files", {}).items():
        name = _match(fname, project_files)
        if name is None:
            continue
        for ln in f.get("executed_lines", []):
            cov.lines.add((name, ln))
            cov.all_lines.add((name, ln))
        for ln in f.get("missing_lines", []):
            cov.all_lines.add((name, ln))
        for a, b in f.get("executed_branches", []):
            cov.branches.add((name, a, b))
            cov.all_branches.add((name, a, b))
        for a, b in f.get("missing_branches", []):
            cov.all_branches.add((name, a, b))
    return cov


def _match(path: str, project_files: set[str]) -> str | None:
    p = path.replace("\\", "/")
    p = p.removeprefix("/work/orig/")
    p = p.lstrip("./")
    if p in project_files:
        return p
    for f in project_files:
        if p.endswith("/" + f) or f.endswith("/" + p):
            return f
    return None
