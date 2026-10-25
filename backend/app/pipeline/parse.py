import re
from dataclasses import dataclass, field

import tree_sitter_cpp
import tree_sitter_python
from tree_sitter import Language, Node, Parser

_LANGS = {
    "python": Language(tree_sitter_python.language()),
    "cpp": Language(tree_sitter_cpp.language()),
}

HARD_CONSTRUCTS = {
    "python": [r"\beval\(", r"\bexec\(", r"\bgetattr\(", r"\bsetattr\(", r"\bimport (numpy|pandas|torch)\b"],
    "cpp": [r"\btemplate\s*<", r"\bvirtual\b", r"\breinterpret_cast\b", r"\bgoto\b", r"\bunion\b"],
}


@dataclass
class ParseResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    has_entrypoint: bool = False
    warnings: list[str] = field(default_factory=list)


def _walk(node: Node):
    yield node
    for c in node.children:
        yield from _walk(c)


def parse(language: str, code: str) -> ParseResult:
    parser = Parser(_LANGS[language])
    tree = parser.parse(code.encode())
    res = ParseResult(ok=True)

    for n in _walk(tree.root_node):
        if n.is_error or n.is_missing:
            res.ok = False
            line = n.start_point[0] + 1
            res.errors.append(f"syntax error at line {line}")
            if len(res.errors) >= 5:
                break

    if language == "python":
        for n in _walk(tree.root_node):
            if n.type == "function_definition":
                name = n.child_by_field_name("name")
                if name is not None and name.text:
                    res.functions.append(name.text.decode())
        res.has_entrypoint = bool(
            re.search(r"__name__\s*==\s*['\"]__main__['\"]", code)
            or re.search(r"\binput\(|sys\.stdin", code)
        )
    else:
        for n in _walk(tree.root_node):
            if n.type == "function_definition":
                decl = n.child_by_field_name("declarator")
                if decl is not None and decl.text:
                    res.functions.append(decl.text.decode().split("(")[0].strip())
        res.has_entrypoint = bool(re.search(r"\bint\s+main\s*\(", code))

    for pat in HARD_CONSTRUCTS[language]:
        if re.search(pat, code):
            res.warnings.append(f"hard construct: {pat}")
    return res
