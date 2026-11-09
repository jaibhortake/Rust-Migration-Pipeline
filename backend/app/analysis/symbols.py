"""Symbol extraction with tree-sitter: imports/includes, classes (bases, methods, fields), functions, complexity."""

import re
from dataclasses import asdict, dataclass, field

import tree_sitter_cpp
import tree_sitter_python
from tree_sitter import Language, Node, Parser

_LANGS = {"python": Language(tree_sitter_python.language()), "cpp": Language(tree_sitter_cpp.language())}

BRANCH_NODES = {
    "python": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",
        "conditional_expression",
        "if_clause",
        "for_in_clause",
        "case_clause",
    },
    "cpp": {
        "if_statement",
        "for_statement",
        "for_range_loop",
        "while_statement",
        "do_statement",
        "case_statement",
        "catch_clause",
        "conditional_expression",
    },
}


@dataclass
class Method:
    name: str
    line: int
    virtual: bool = False
    pure: bool = False
    static: bool = False
    operator: bool = False


@dataclass
class ClassInfo:
    name: str
    file: str
    line: int
    bases: list[str] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    is_abstract: bool = False
    is_exception: bool = False
    is_template: bool = False
    is_struct: bool = False


@dataclass
class Function:
    name: str
    line: int
    loc: int
    complexity: int
    recursive: bool = False
    owner: str | None = None  # class name for methods / out-of-class definitions


@dataclass
class Import:
    module: str  # python dotted module ("." prefixes kept for relative) or include path
    line: int
    system: bool = False  # <header> or a non-project module
    names: list[str] = field(default_factory=list)


@dataclass
class FileSymbols:
    path: str
    loc: int = 0
    complexity: int = 1
    has_entrypoint: bool = False
    syntax_errors: list[int] = field(default_factory=list)
    has_calls: bool = False
    imports: list[Import] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def walk(node: Node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def text(n: Node | None) -> str:
    return n.text.decode(errors="replace") if n is not None and n.text else ""


def parse_tree(language: str, code: str):
    return Parser(_LANGS[language]).parse(code.encode())


def _complexity(language: str, node: Node) -> int:
    c = 1
    for n in walk(node):
        if n.type in BRANCH_NODES[language]:
            c += 1
        elif language == "cpp" and n.type == "binary_expression":
            op = n.child_by_field_name("operator")
            if op is not None and op.type in ("&&", "||", "and", "or"):
                c += 1
    return c


def _loc(node: Node) -> int:
    return node.end_point[0] - node.start_point[0] + 1


def _calls(node: Node, name: str) -> bool:
    short = name.split("::")[-1]
    for n in walk(node):
        if n.type in ("call", "call_expression"):
            f = n.child_by_field_name("function")
            t = text(f)
            if t in (short, "self." + short, "this->" + short) or (t.endswith("::" + short) and "super" not in t):
                return True
    return False


def extract(language: str, path: str, code: str) -> FileSymbols:
    tree = parse_tree(language, code)
    fs = FileSymbols(path=path, loc=len([ln for ln in code.splitlines() if ln.strip()]))
    for n in walk(tree.root_node):
        if n.type in ("call", "call_expression"):
            fs.has_calls = True
        if (n.is_error or n.is_missing) and len(fs.syntax_errors) < 5:
            fs.syntax_errors.append(n.start_point[0] + 1)
    fs.complexity = _complexity(language, tree.root_node)
    (_python if language == "python" else _cpp)(fs, tree.root_node, code)
    return fs


# ---------------------------------------------------------------- Python


def _python(fs: FileSymbols, root: Node, code: str) -> None:
    fs.has_entrypoint = bool(re.search(r"__name__\s*==\s*['\"]__main__['\"]", code) or re.search(r"\binput\(|sys\.stdin", code))
    for n in walk(root):
        if n.type == "import_statement":
            for c in n.named_children:
                mod = text(c.child_by_field_name("name") if c.type == "aliased_import" else c)
                fs.imports.append(Import(mod, n.start_point[0] + 1))
        elif n.type == "import_from_statement":
            mod_node = n.child_by_field_name("module_name")
            names = [text(c.child_by_field_name("name") if c.type == "aliased_import" else c) for c in n.children_by_field_name("name")]
            fs.imports.append(Import(text(mod_node), n.start_point[0] + 1, names=names))
        elif n.type == "class_definition":
            fs.classes.append(_py_class(fs.path, n))
        elif n.type == "function_definition":
            name = text(n.child_by_field_name("name"))
            owner = _py_owner(n)
            fs.functions.append(
                Function(
                    name,
                    n.start_point[0] + 1,
                    _loc(n),
                    _complexity("python", n),
                    recursive=_calls(n.child_by_field_name("body"), name),
                    owner=owner,
                )
            )


def _py_owner(n: Node) -> str | None:
    p = n.parent
    while p is not None:
        if p.type == "class_definition":
            return text(p.child_by_field_name("name"))
        if p.type == "function_definition":
            return None
        p = p.parent
    return None


def _decorators(n: Node) -> list[str]:
    p = n.parent
    if p is not None and p.type == "decorated_definition":
        return [text(d).lstrip("@").split("(")[0].strip() for d in p.children if d.type == "decorator"]
    return []


def _py_class(path: str, n: Node) -> ClassInfo:
    ci = ClassInfo(text(n.child_by_field_name("name")), path, n.start_point[0] + 1)
    sup = n.child_by_field_name("superclasses")
    if sup is not None:
        ci.bases = [text(c) for c in sup.named_children if c.type != "keyword_argument"]
        if any(text(c).startswith("metaclass") for c in sup.named_children):
            ci.decorators.append("metaclass")
    ci.decorators += _decorators(n)
    body = n.child_by_field_name("body")
    fields: list[str] = []
    for c in body.named_children if body is not None else []:
        fn = c.child_by_field_name("definition") if c.type == "decorated_definition" else c
        if fn is not None and fn.type == "function_definition":
            name = text(fn.child_by_field_name("name"))
            decs = _decorators(fn)
            ci.methods.append(
                Method(
                    name,
                    fn.start_point[0] + 1,
                    static="staticmethod" in decs or "classmethod" in decs,
                    operator=name.startswith("__") and name.endswith("__") and name != "__init__",
                    pure="abstractmethod" in decs or "raise NotImplementedError" in text(fn),
                )
            )
            if name == "__init__":
                fields += re.findall(r"self\.(\w+)\s*(?::[^=\n]+)?=(?!=)", text(fn))
        elif c.type == "expression_statement":
            m = re.match(r"(\w+)\s*:", text(c))
            if m:
                fields.append(m.group(1))
    ci.fields = list(dict.fromkeys(fields))
    ci.is_abstract = any(m.pure for m in ci.methods) or any(b in ("ABC", "abc.ABC", "Protocol") for b in ci.bases)
    ci.is_exception = any(re.search(r"(Error|Exception)$", b) for b in ci.bases)
    ci.is_struct = "dataclass" in ci.decorators or any(b.endswith("NamedTuple") for b in ci.bases)
    return ci


# ---------------------------------------------------------------- C++


def _ident(n: Node | None) -> str:
    """Innermost name of a declarator."""
    while n is not None:
        if n.type in ("identifier", "field_identifier", "type_identifier", "operator_name", "destructor_name", "qualified_identifier"):
            return text(n)
        nxt = n.child_by_field_name("declarator")
        if nxt is None:
            names = [c for c in n.named_children if c.type in ("identifier", "field_identifier")]
            return text(names[0]) if names else ""
        n = nxt
    return ""


def _has_func_declarator(n: Node | None) -> bool:
    while n is not None:
        if n.type == "function_declarator":
            return True
        n = n.child_by_field_name("declarator")
    return False


def _cpp(fs: FileSymbols, root: Node, code: str) -> None:
    fs.has_entrypoint = bool(re.search(r"\bint\s+main\s*\(", code))
    for n in walk(root):
        if n.type == "preproc_include":
            p = n.child_by_field_name("path")
            raw = text(p)
            fs.imports.append(Import(raw.strip('"<>'), n.start_point[0] + 1, system=raw.startswith("<")))
        elif n.type in ("class_specifier", "struct_specifier") and n.child_by_field_name("body") is not None:
            name = text(n.child_by_field_name("name"))
            if name:
                fs.classes.append(_cpp_class(fs.path, n, name))
        elif n.type == "function_definition":
            name = _ident(n.child_by_field_name("declarator"))
            owner = None
            if "::" in name:
                owner = name.rsplit("::", 1)[0].split("<")[0]
            else:
                p = n.parent
                while p is not None and p.type not in ("class_specifier", "struct_specifier", "translation_unit"):
                    p = p.parent
                if p is not None and p.type != "translation_unit":
                    owner = text(p.child_by_field_name("name"))
            fs.functions.append(
                Function(
                    name,
                    n.start_point[0] + 1,
                    _loc(n),
                    _complexity("cpp", n),
                    recursive=_calls(n.child_by_field_name("body") or n, name),
                    owner=owner,
                )
            )


def _cpp_class(path: str, n: Node, name: str) -> ClassInfo:
    ci = ClassInfo(name, path, n.start_point[0] + 1, is_struct=n.type == "struct_specifier")
    ci.is_template = n.parent is not None and n.parent.type == "template_declaration"
    for c in n.named_children:
        if c.type == "base_class_clause":
            ci.bases = [
                text(b).split("<")[0] for b in c.named_children if b.type in ("type_identifier", "qualified_identifier", "template_type")
            ]
    body = n.child_by_field_name("body")
    for c in body.named_children if body is not None else []:
        if c.type == "template_declaration":
            c = next((x for x in c.named_children if x.type in ("function_definition", "field_declaration", "declaration")), c)
        t = text(c)
        if c.type in ("field_declaration", "declaration", "function_definition"):
            decl = c.child_by_field_name("declarator")
            if c.type == "function_definition" or _has_func_declarator(decl):
                mname = _ident(decl)
                ci.methods.append(
                    Method(
                        mname,
                        c.start_point[0] + 1,
                        virtual=bool(re.match(r"\s*virtual\b", t)) or bool(re.search(r"\boverride\b", t)),
                        pure=bool(re.search(r"=\s*0\s*;\s*$", t)),
                        static=bool(re.match(r"\s*static\b", t)),
                        operator=mname.startswith("operator") or mname.startswith("~"),
                    )
                )
            else:
                for d in c.children_by_field_name("declarator"):
                    fname = _ident(d)
                    if fname:
                        ci.fields.append(fname)
    ci.is_abstract = any(m.pure for m in ci.methods)
    ci.is_exception = any(re.search(r"(exception|error)$", b, re.IGNORECASE) for b in ci.bases)
    return ci
