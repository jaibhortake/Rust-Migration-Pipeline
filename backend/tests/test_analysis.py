import io
import zipfile

import pytest
from conftest import load_dir

from app.analysis.assess import analyze
from app.analysis.graph import module_name
from app.analysis.project import ProjectError, build_project, clean_path, files_from_zip
from app.analysis.symbols import extract


def test_clean_path_rejects_traversal():
    for bad in ["../x.py", "/etc/passwd.py", "C:/x.py", "a/../../b.py", ""]:
        with pytest.raises(ProjectError):
            clean_path(bad)
    assert clean_path("pkg\\mod.py") == "pkg/mod.py"


def test_zip_strips_common_root_and_skips_junk():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("proj/main.py", "print(1)\n")
        z.writestr("proj/lib/util.py", "X = 1\n")
        z.writestr("proj/__pycache__/x.py", "junk")
        z.writestr("proj/README.md", "hi")
    files = files_from_zip(buf.getvalue())
    assert set(files) == {"main.py", "lib/util.py"}


def test_zip_slip_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.py", "x")
    with pytest.raises(ProjectError):
        files_from_zip(buf.getvalue())


def test_mixed_languages_rejected():
    with pytest.raises(ProjectError):
        build_project({"a.py": "x=1", "b.cpp": "int main(){}"})


def test_module_names_are_valid_rust_identifiers():
    assert module_name("main.py") == "m_main"
    assert module_name("pkg/__init__.py") == "pkg"
    assert module_name("2d-grid.cpp") == "m_2d_grid"
    assert module_name("utils/str ops.py") == "utils_str_ops"


def test_python_symbols():
    code = (
        "from abc import ABC, abstractmethod\n"
        "class A(ABC):\n"
        "    def __init__(self, x):\n        self.x = x\n        self.y: int = 0\n"
        "    @abstractmethod\n    def f(self): ...\n"
        "    def __eq__(self, o): return self.x == o.x\n"
        "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n"
    )
    s = extract("python", "a.py", code)
    a = s.classes[0]
    assert a.is_abstract and a.fields == ["x", "y"] and a.bases == ["ABC"]
    fact = next(f for f in s.functions if f.name == "fact")
    assert fact.recursive and fact.complexity >= 2
    init = next(f for f in s.functions if f.name == "__init__")
    assert not init.recursive


def test_super_init_is_not_recursion():
    code = "class B(A):\n    def __init__(self):\n        super().__init__()\n"
    assert not extract("python", "b.py", code).functions[0].recursive


def test_cpp_symbols():
    code = (
        '#include "shape.h"\n#include <vector>\n'
        "class Sq : public Shape {\npublic:\n  double area() const override;\n  virtual void f() = 0;\n"
        "  static int count();\nprivate:\n  double side_;\n};\n"
        "double Sq::area() const { return side_ * side_; }\n"
    )
    s = extract("cpp", "sq.h", code)
    c = s.classes[0]
    assert c.bases == ["Shape"] and c.fields == ["side_"] and c.is_abstract
    assert {m.name for m in c.methods} == {"area", "f", "count"}
    assert [i.module for i in s.imports] == ["shape.h", "vector"] and s.imports[1].system
    assert s.functions[0].owner == "Sq"


def test_python_project_graph_and_mappings():
    a, m = analyze(build_project(load_dir("py_inventory")))
    assert a["graph"]["order"] == [["models"], ["inventory"], ["m_main"]]
    assert a["graph"]["entry"] == "m_main"
    strategies = {c["name"]: c["strategy"] for c in m["classes"]}
    assert strategies == {"Item": "trait", "Book": "implementor", "Food": "implementor", "Line": "data", "Inventory": "struct"}
    rules = {r["rule"] for r in a["risks"]}
    assert {"floor-div", "dict-order"} <= rules
    assert "monkeypatch" not in rules and "recursion" not in rules


def test_cpp_project_graph_units_pair_headers_and_sources():
    a, m = analyze(build_project(load_dir("cpp_shapes")))
    units = a["graph"]["units"]
    assert units["circle"]["files"] == ["circle.h", "circle.cpp"]
    assert set(units["m_main"]["deps"]) == {"circle", "rect"}
    order = [g[0] for g in a["graph"]["order"]]
    assert order.index("shape") < order.index("circle") and order[-1] == "m_main"
    strategies = {c["name"]: c["strategy"] for c in m["classes"]}
    assert strategies["Shape"] == "trait" and strategies["Circle"] == "implementor"
    assert a["summary"]["readiness"] == "easy"


def test_cycles_are_grouped():
    files = {"a.py": "import b\n", "b.py": "import a\n", "main.py": "import a\nprint(input())\n"}
    a, _ = analyze(build_project(files))
    assert ["a", "b"] in a["graph"]["cycles"]
    assert a["graph"]["order"][-1] == ["m_main"]


def test_exception_class_maps_to_error():
    _, m = analyze(build_project(load_dir("py_bank")))
    s = {c["name"]: c for c in m["classes"]}
    assert s["InsufficientFunds"]["strategy"] == "error"
    assert "PartialOrd/Ord" in s["Account"]["trait_impls"]


def test_blockers():
    a, _ = analyze(build_project({"a.py": "def f(:\n", "b.py": "x = 1\n"}))
    assert a["summary"]["readiness"] == "blocked"


def test_single_function_detected():
    a, _ = analyze(build_project({"f.py": "def add(a, b):\n    return a + b\n"}))
    assert a["summary"]["single_function"] and not a["summary"]["blockers"]


def test_library_mapping_kinds():
    files = {"main.py": "import re, random, heapq\nimport numpy\nprint(input())\n"}
    _, m = analyze(build_project(files))
    kinds = {x["source"]: x["kind"] for x in m["libraries"]}
    assert kinds["re"] == "crate" and kinds["random"] == "unsupported" and kinds["heapq"] == "std"
    assert kinds["numpy"] == "manual"


def test_program_output_pasted_as_source_is_blocked_not_wrapped():
    """Regression: output text uploaded as main.cpp used to be 'wrapped' by the LLM into an empty main()."""
    out = "===== STRESS TEST =====\n\n[1] Statistics\nSum: 150\nAverage: 30\n"
    a, _ = analyze(build_project({"main.cpp": out}))
    s = a["summary"]
    assert s["readiness"] == "blocked" and not s["single_function"]
    assert any("does not look like C++ source" in b for b in s["blockers"])


def test_file_without_any_code_is_blocked():
    a, _ = analyze(build_project({"x.py": "# just a comment\nX = 1\n"}))
    assert a["summary"]["readiness"] == "blocked" and not a["summary"]["single_function"]


def test_requirements_and_cmake_manifests():
    from app.analysis.manifest import parse_cmake, parse_requirements

    assert parse_requirements("numpy>=1.2  # fast\nrequests[security]==2.0\n-r other.txt\nPyYAML\n") == ["numpy", "requests", "pyyaml"]
    cm = parse_cmake(
        "set(CMAKE_CXX_STANDARD 17)\nadd_executable(app main.cpp util.cpp)\nadd_executable(tool tool.cpp)\n"
        "include_directories(include)\nfind_package(Threads)\n",
        "",
    )
    assert cm["std"] == 17 and cm["targets"]["app"]["sources"] == ["main.cpp", "util.cpp"] and cm["include_dirs"] == ["include"]

    files = {
        "CMakeLists.txt": "add_executable(app main.cpp util.cpp)\nadd_executable(tool tool.cpp)\n",
        "main.cpp": '#include "util.h"\nint main(){return f();}\n',
        "util.cpp": "int f(){return 1;}\n",
        "util.h": "int f();\n",
        "tool.cpp": "int main(){return 0;}\n",
    }
    p = build_project(files)
    assert set(p.files) == {"main.cpp", "util.cpp", "util.h"} and p.manifest["cmake"]["selected_target"] == "app"
    a, _ = analyze(p)  # two mains would have been a blocker without the CMake target selection
    assert not a["summary"]["blockers"]


def test_requirements_flag_unsupported_libraries_up_front():
    files = {"requirements.txt": "pandas\nnumpy\n", "main.py": "import sys\nprint(sys.argv)\n"}
    a, m = analyze(build_project(files))
    kinds = {x["source"]: x["kind"] for x in m["libraries"]}
    assert kinds["pandas"] == "unsupported" and kinds["numpy"] == "manual"
    assert a["summary"]["manifest"]["requirements"] == ["pandas", "numpy"]


def test_reads_stdin_detection():
    from app.analysis.assess import reads_stdin

    assert reads_stdin("cpp", {"a.cpp": "int main(){int x; std::cin >> x;}"})
    assert reads_stdin("python", {"a.py": "n = int(input())"})
    assert not reads_stdin("cpp", {"a.cpp": "int main(){ std::cout << 1; }"})
    assert not reads_stdin("python", {"a.py": "print(1 + 2)"})
