"""Class mapping: how each class becomes Rust types, with the reason.

Rust has no inheritance. The strategy is chosen from the class's role in the hierarchy:
  struct       plain data + behaviour                      -> struct + impl
  data         dataclass / POD struct                      -> #[derive(...)] struct
  trait        abstract base / interface                   -> trait (+ shared state struct if it has fields)
  implementor  subclass of an abstract base                -> struct + impl Trait for Struct
  enum         closed hierarchy (all subclasses known, small, no extension) -> enum with one variant per subclass
  composition  subclass of a concrete class                -> struct that embeds the base struct as a field
  error        exception class                             -> variant of an error enum implementing std::error::Error
"""

from dataclasses import asdict, dataclass, field

from app.analysis.symbols import ClassInfo

STRATEGIES = ["struct", "data", "trait", "implementor", "enum", "composition", "error"]

PY_TRAITS = {
    "__eq__": "PartialEq",
    "__ne__": "PartialEq",
    "__lt__": "PartialOrd/Ord",
    "__le__": "PartialOrd/Ord",
    "__gt__": "PartialOrd/Ord",
    "__ge__": "PartialOrd/Ord",
    "__hash__": "Hash",
    "__str__": "Display",
    "__repr__": "Debug",
    "__add__": "std::ops::Add",
    "__sub__": "std::ops::Sub",
    "__mul__": "std::ops::Mul",
    "__truediv__": "std::ops::Div",
    "__neg__": "std::ops::Neg",
    "__len__": "fn len(&self)",
    "__iter__": "IntoIterator / Iterator",
    "__next__": "Iterator",
    "__getitem__": "std::ops::Index",
    "__setitem__": "std::ops::IndexMut",
    "__contains__": "fn contains(&self)",
    "__call__": "method or closure",
    "__enter__": "RAII guard + Drop",
    "__exit__": "Drop",
    "__del__": "Drop",
    "__bool__": "fn is_truthy(&self)",
    "__lt__ only": "PartialOrd",
}
CPP_TRAITS = {
    "operator==": "PartialEq",
    "operator!=": "PartialEq",
    "operator<": "PartialOrd/Ord",
    "operator>": "PartialOrd/Ord",
    "operator<=": "PartialOrd/Ord",
    "operator>=": "PartialOrd/Ord",
    "operator<=>": "PartialOrd/Ord",
    "operator+": "std::ops::Add",
    "operator-": "std::ops::Sub",
    "operator*": "std::ops::Mul (or Deref)",
    "operator/": "std::ops::Div",
    "operator+=": "std::ops::AddAssign",
    "operator-=": "std::ops::SubAssign",
    "operator[]": "std::ops::Index / IndexMut",
    "operator()": "method or closure",
    "operator<<": "Display",
    "operator=": "Clone (copy assignment)",
    "operator bool": "fn is_valid(&self)",
}


@dataclass
class ClassMapping:
    name: str
    file: str
    line: int
    source_kind: str
    strategy: str
    target: str
    trait_impls: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    rationale: str = ""
    notes: str = ""  # free text the user can add; passed to the translator

    def to_dict(self) -> dict:
        return asdict(self)


def map_classes(language: str, classes: list[ClassInfo]) -> list[ClassMapping]:
    by_name = {c.name: c for c in classes}
    children: dict[str, list[str]] = {}
    for c in classes:
        for b in c.bases:
            children.setdefault(b.split("::")[-1], []).append(c.name)

    out = []
    for c in classes:
        kids = children.get(c.name, [])
        project_bases = [b.split("::")[-1] for b in c.bases if b.split("::")[-1] in by_name]
        has_virtual = any(m.virtual for m in c.methods)
        kind = "struct" if c.is_struct else "class"
        if c.is_template:
            kind = "template " + kind

        if c.is_exception:
            strategy, rationale = "error", "Exceptions become values: one variant of an error enum returned in Result."
        elif kids and (c.is_abstract or has_virtual or language == "python"):
            closed = len(kids) <= 5 and not c.fields and all(not children.get(k) for k in kids)
            if closed and not c.is_abstract and language == "cpp":
                strategy = "enum"
                rationale = (
                    f"Small closed hierarchy ({', '.join(kids)}) without shared state: an enum with one variant "
                    "per subclass and a match per method is simplest and avoids dynamic dispatch."
                )
            else:
                strategy = "trait"
                rationale = (
                    f"Base of {', '.join(kids)} used polymorphically: a trait with the overridable methods; "
                    "callers hold Box<dyn " + c.name + "> or use generics."
                )
                if c.fields:
                    rationale += f" Shared fields ({', '.join(c.fields[:5])}) move into a {c.name}Base struct each implementor embeds."
        elif project_bases and any(
            by_name[b].is_abstract or any(m.virtual for m in by_name[b].methods) or language == "python" and children.get(b)
            for b in project_bases
        ):
            strategy = "implementor"
            rationale = f"Implements the {', '.join(project_bases)} trait(s); own fields stay in this struct."
        elif project_bases:
            strategy = "composition"
            rationale = (
                f"Inherits from concrete {', '.join(project_bases)}: embed it as a field (base: "
                f"{project_bases[0]}) and delegate the inherited methods."
            )
        elif c.is_struct or (not c.methods or all(m.name in ("__init__", "__repr__", "__eq__") for m in c.methods)):
            strategy, rationale = "data", "Plain data: a struct with derived Debug/Clone/PartialEq."
        else:
            strategy, rationale = "struct", "Data plus behaviour: a struct with an impl block; the constructor becomes new()."

        out.append(
            ClassMapping(
                name=c.name,
                file=c.file,
                line=c.line,
                source_kind=kind,
                strategy=strategy,
                target=_target(c, strategy, project_bases),
                trait_impls=_trait_impls(language, c),
                members=_members(language, c),
                rationale=rationale,
            )
        )
    return out


def _target(c: ClassInfo, strategy: str, bases: list[str]) -> str:
    generic = "<T>" if c.is_template else ""
    return {
        "error": f"enum {c.name} (impl std::error::Error)",
        "trait": f"trait {c.name}" + (f" + struct {c.name}Base" if c.fields else ""),
        "enum": f"enum {c.name} {{ ...variants }}",
        "implementor": f"struct {c.name}{generic} + impl {' + '.join(bases)} for {c.name}",
        "composition": f"struct {c.name}{generic} {{ base: {bases[0] if bases else '?'}, ... }}",
        "data": f"#[derive(Debug, Clone, PartialEq)] struct {c.name}{generic}",
        "struct": f"struct {c.name}{generic} + impl {c.name}",
    }[strategy]


def _trait_impls(language: str, c: ClassInfo) -> list[str]:
    table = PY_TRAITS if language == "python" else CPP_TRAITS
    found = []
    for m in c.methods:
        name = m.name.replace(" ", "")
        t = table.get(name)
        if t is None and name.startswith("~"):
            t = "Drop (often unnecessary: owned fields free themselves)"
        if t and t not in found:
            found.append(t)
    return found


def _members(language: str, c: ClassInfo) -> list[str]:
    out = [f"field {f}" for f in c.fields[:12]]
    for m in c.methods[:20]:
        if m.name in ("__init__", c.name):
            out.append(f"{m.name} -> fn new(..) -> Self")
        elif m.static:
            out.append(f"{m.name} -> associated fn (no self)")
        elif m.pure:
            out.append(f"{m.name} -> required trait method")
        elif m.virtual:
            out.append(f"{m.name} -> trait method (overridable)")
    return out
