"""Module units, dependency edges between them, strongly connected components and a leaves-first order.

A unit is what becomes one Rust module: a Python file, or a C++ header/source pair with the same stem.
"""

import posixpath
from dataclasses import asdict, dataclass, field

from app.analysis.project import CPP_HEADERS, CPP_SOURCES, Project
from app.analysis.symbols import FileSymbols


@dataclass
class Unit:
    id: str  # also the Rust module name for non-entry units
    files: list[str]
    is_entry: bool = False
    deps: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)  # libraries / system headers it uses


@dataclass
class Graph:
    units: dict[str, Unit]
    order: list[list[str]]  # groups of unit ids, leaves first; a group with >1 id is a dependency cycle
    entry: str | None

    @property
    def cycles(self) -> list[list[str]]:
        return [g for g in self.order if len(g) > 1]

    def to_dict(self) -> dict:
        return {"units": {k: asdict(u) for k, u in self.units.items()}, "order": self.order, "entry": self.entry, "cycles": self.cycles}


RUST_KEYWORDS = {
    "as",
    "break",
    "const",
    "continue",
    "crate",
    "else",
    "enum",
    "extern",
    "false",
    "fn",
    "for",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "match",
    "mod",
    "move",
    "mut",
    "pub",
    "ref",
    "return",
    "self",
    "Self",
    "static",
    "struct",
    "super",
    "trait",
    "true",
    "type",
    "unsafe",
    "use",
    "where",
    "while",
    "async",
    "await",
    "dyn",
    "main",
    "std",
    "core",
    "test",
    "tests",
    "lib",
}


def module_name(path: str) -> str:
    stem = posixpath.splitext(path)[0]
    stem = stem.removesuffix("/__init__")
    name = "".join(c if c.isalnum() else "_" for c in stem.replace("/", "_")).lower().strip("_") or "module"
    if name[0].isdigit() or name in RUST_KEYWORDS:
        name = "m_" + name
    return name


def build_graph(project: Project, symbols: dict[str, FileSymbols]) -> Graph:
    units = _python_units(project, symbols) if project.language == "python" else _cpp_units(project, symbols)
    entries = [u.id for u in units.values() if u.is_entry]
    order = _scc_order(units)
    return Graph(units, order, entries[0] if len(entries) == 1 else None)


def _python_units(project: Project, symbols: dict[str, FileSymbols]) -> dict[str, Unit]:
    by_module: dict[str, str] = {}  # dotted module -> unit id
    units: dict[str, Unit] = {}
    for path in project.files:
        uid = module_name(path)
        units[uid] = Unit(uid, [path], is_entry=symbols[path].has_entrypoint)
        dotted = posixpath.splitext(path)[0].replace("/", ".")
        dotted = dotted.removesuffix(".__init__")
        by_module[dotted] = uid
        by_module.setdefault(dotted.split(".")[-1], uid)  # flat imports of sibling files

    for path in project.files:
        uid = module_name(path)
        pkg = posixpath.dirname(path).replace("/", ".")
        for imp in symbols[path].imports:
            mod = imp.module
            if mod.startswith("."):
                level = len(mod) - len(mod.lstrip("."))
                base = pkg.split(".") if pkg else []
                base = base[: len(base) - (level - 1)] if level > 1 else base
                rest = mod.lstrip(".")
                candidates = [".".join([*base, rest]).strip(".")] if rest else [".".join([*base, n]).strip(".") for n in imp.names]
            else:
                candidates = [mod, *(f"{mod}.{n}" for n in imp.names)]
            hit = [by_module[c] for c in candidates if c in by_module and by_module[c] != uid]
            if hit:
                for h in hit:
                    if h not in units[uid].deps:
                        units[uid].deps.append(h)
            elif mod and not mod.startswith("."):
                top = mod.split(".")[0]
                if top not in units[uid].external:
                    units[uid].external.append(top)
    return units


def _cpp_units(project: Project, symbols: dict[str, FileSymbols]) -> dict[str, Unit]:
    stems: dict[str, list[str]] = {}
    for path in project.files:
        stems.setdefault(posixpath.splitext(path)[0], []).append(path)
    units: dict[str, Unit] = {}
    file_unit: dict[str, str] = {}
    for stem, files in stems.items():
        uid = module_name(stem)
        files.sort(key=lambda p: (not p.endswith(CPP_HEADERS), p))  # header first
        is_entry = any(symbols[f].has_entrypoint for f in files if f.endswith(CPP_SOURCES))
        units[uid] = Unit(uid, files, is_entry=is_entry)
        for f in files:
            file_unit[f] = uid
    basenames: dict[str, list[str]] = {}
    for path in project.files:
        basenames.setdefault(posixpath.basename(path), []).append(path)

    for path in project.files:
        uid = file_unit[path]
        for imp in symbols[path].imports:
            target = None
            if not imp.system:
                rel = posixpath.normpath(posixpath.join(posixpath.dirname(path), imp.module))
                if rel in project.files:
                    target = rel
                elif imp.module in project.files:
                    target = imp.module
                elif len(basenames.get(posixpath.basename(imp.module), [])) == 1:
                    target = basenames[posixpath.basename(imp.module)][0]
            if target is not None:
                t = file_unit[target]
                if t != uid and t not in units[uid].deps:
                    units[uid].deps.append(t)
            elif imp.module not in units[uid].external:
                units[uid].external.append(imp.module)
    return units


def _scc_order(units: dict[str, Unit]) -> list[list[str]]:
    """Tarjan's algorithm. Emits components in reverse topological order = dependencies first."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = [0]

    def visit(v: str) -> None:
        # iterative to avoid recursion limits on large graphs
        work = [(v, iter(units[v].deps))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in units:
                    continue
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(units[w].deps)))
                    advanced = True
                    break
                if w in on_stack:
                    low[node] = min(low[node], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                out.append(sorted(comp))

    for v in sorted(units):
        if v not in index:
            visit(v)
    # entry unit always last
    return sorted(out, key=lambda g: any(units[u].is_entry for u in g))
