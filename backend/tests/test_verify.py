import gzip
import json
import random

from app.mapping.libraries import crates_for
from app.pipeline.runner import compare, extract_files, parse_json_list, public_api, with_mods
from app.verify.coverage import Coverage, parse_coveragepy, parse_gcov_dir
from app.verify.fuzz import minimize, mutations
from app.verify.quality import parse_clippy, score


def test_compare_exact_numeric_diff():
    assert compare("a 1\nb\n", "a 1  \nb") == "exact"
    assert compare("x 0.30000000000000004", "x 0.3") == "numeric"
    assert compare("x 0.31", "x 0.3") == "diff"
    assert compare("1 2", "1 2 3") == "diff"


def test_extract_files_labeled_and_default():
    text = "```rust\n// file: src/a.rs\npub fn a() {}\n```\n```rust\n// file: ../evil.rs\nx\n```"
    assert extract_files(text) == {"src/a.rs": "pub fn a() {}\n"}
    assert extract_files("```rust\nfn main() {}\n```", "src/main.rs") == {"src/main.rs": "fn main() {}\n"}


def test_with_mods_inserts_after_inner_attributes_and_dedupes():
    out = with_mods("#![allow(dead_code)]\nmod shape;\nuse crate::shape::Shape;\nfn main() {}\n", ["circle", "shape"])
    lines = out.splitlines()
    assert lines[0] == "#![allow(dead_code)]" and lines[1:3] == ["mod circle;", "mod shape;"]
    assert out.count("mod shape;") == 1


def test_public_api():
    rust = "pub struct A {\n  x: i32,\n}\nimpl A {\n    pub fn new() -> Self {\n        A { x: 1 }\n    }\n    fn private() {}\n}\n"
    api = public_api(rust)
    assert "pub struct A" in api and "pub fn new() -> Self" in api and "private" not in api


def test_parse_json_list():
    assert parse_json_list('Here: ["1\\n", "2"] ok') == ["1\n", "2"]
    assert parse_json_list("[1, 2]") == ["1", "2"]
    assert parse_json_list("nope") is None


def test_mutations_are_deterministic_and_distinct():
    a = mutations("3\n1 2 3\n", random.Random(1), 5)
    b = mutations("3\n1 2 3\n", random.Random(1), 5)
    assert a == b and len(set(a)) == len(a) and "3\n1 2 3\n" not in a


async def test_minimize_finds_smaller_failing_input():
    # bug: fails whenever a negative number is present
    async def still_fails(s: str) -> bool:
        return "-" in s

    small = await minimize("5\n1\n2\n-7\n3\n4\n", still_fails, budget=60)
    assert "-" in small and len(small.splitlines()) == 1


def test_coverage_merge_and_rates(tmp_path):
    data = {
        "files": [
            {
                "file": "main.cpp",
                "lines": [
                    {"line_number": 1, "count": 1, "branches": [{"count": 1, "throw": False}, {"count": 0, "throw": False}]},
                    {"line_number": 2, "count": 0, "branches": [{"count": 0, "throw": True}]},
                ],
            },
            {"file": "/usr/include/c++/12/iostream", "lines": [{"line_number": 5, "count": 1, "branches": []}]},
        ]
    }
    (tmp_path / "main.gcov.json.gz").write_bytes(gzip.compress(json.dumps(data).encode()))
    cov = parse_gcov_dir(tmp_path, {"main.cpp"})
    assert cov.line_rate == 0.5 and cov.branch_rate == 0.5  # throw edge ignored, system header ignored
    assert cov.uncovered() == {"main.cpp": [2]}

    pj = tmp_path / "c.json"
    pj.write_text(
        json.dumps(
            {"files": {"main.py": {"executed_lines": [1, 2], "missing_lines": [3], "executed_branches": [[2, 3]], "missing_branches": []}}}
        )
    )
    py = parse_coveragepy(pj, {"main.py"})
    total = Coverage()
    assert py.adds_to(total)
    total.merge(py)
    assert not py.adds_to(total)
    assert round(total.line_rate, 2) == 0.67 and total.branch_rate == 1.0


def test_clippy_parse_and_score():
    msg = {
        "reason": "compiler-message",
        "message": {
            "level": "warning",
            "message": "the loop variable `i` is only used to index `v`",
            "code": {"code": "clippy::needless_range_loop"},
            "spans": [{"is_primary": True, "file_name": "src/main.rs", "line_start": 3}],
        },
    }
    w = parse_clippy(json.dumps(msg) + "\nnot json\n")
    assert w[0]["lint"] == "clippy::needless_range_loop"
    clean = score({"src/main.rs": 'fn main() {\n    println!("hi");\n}\n'}, [], 0)
    dirty = score({"src/main.rs": "fn main() {\n    unsafe { }\n    let x = y.unwrap();\n}\n"}, w, 3)
    assert clean["score"] == 100 and dirty["score"] < 70 and dirty["unsafe"] == 1


def test_crates_only_from_allowlist():
    deps = crates_for([{"kind": "crate", "crates": ["regex", "evil-crate"]}, {"kind": "std", "crates": ["serde"]}])
    assert deps == ['regex = "1"']


def test_coverage_checkpoint_roundtrip():
    cov = Coverage({("a.py", 1), ("a.py", 2)}, {("a.py", 1), ("a.py", 2), ("a.py", 3)}, {("a.py", 2, 0)}, {("a.py", 2, 0), ("a.py", 2, 1)})
    back = Coverage.from_dict(json.loads(json.dumps(cov.to_dict())))
    assert back.lines == cov.lines and back.all_branches == cov.all_branches and back.line_rate == cov.line_rate


def test_extract_block_handles_truncated_reply():
    from app.pipeline.runner import extract_block

    assert extract_block("```rust\nfn main() {\n    let x").startswith("fn main() {")
    assert extract_block("intro ```rust\nfn a() {}\n``` outro") == "fn a() {}\n"


def test_waves_run_independent_modules_together():
    from app.pipeline.runner import Migration

    units = {
        "a": {"deps": []},
        "b": {"deps": []},
        "c": {"deps": ["a", "b"]},
        "m_main": {"deps": ["c"]},
    }
    order = [["a"], ["b"], ["c"], ["m_main"]]
    waves = Migration._waves(None, order, units, "m_main")
    assert waves == [[["a"], ["b"]], [["c"]], [["m_main"]]]


def test_contract_adherence_and_explanations():
    from app.pipeline.explain import contract_adherence, explain

    mappings = {
        "classes": [
            {"name": "Shape", "strategy": "trait"},
            {"name": "Circle", "strategy": "implementor"},
            {"name": "Rect", "strategy": "implementor"},
            {"name": "Oops", "strategy": "error"},
        ],
        "libraries": [{"source": "re", "kind": "crate", "crates": ["regex"]}, {"source": "random", "kind": "unsupported", "crates": []}],
    }
    rust = {
        "src/shape.rs": "pub trait Shape { fn area(&self) -> f64; }\n",
        "src/main.rs": "struct Circle;\nimpl Shape for Circle { }\nstruct Rect;\n",
    }
    c = contract_adherence(mappings, rust)
    by = {r["name"] + r["kind"]: r for r in c["rows"]}
    assert by["Shapeclass"]["followed"] and by["Circleclass"]["followed"]
    assert not by["Rectclass"]["followed"] and "without a trait impl" in by["Rectclass"]["detail"]
    assert not by["Oopsclass"]["followed"] and not by["relibrary"]["followed"] and by["randomlibrary"]["followed"]
    assert c["followed"] == 3 and c["total"] == 6

    assert explain({"status": "failed", "message": "the original C++ does not compile"})["title"].startswith("Your C++")
    assert "Nothing to compare" == explain({"status": "failed", "message": "the original program prints nothing on every input"})["title"]
    assert explain({"status": "equivalent", "confidence": "high"})["title"].startswith("Behaviour matches")
