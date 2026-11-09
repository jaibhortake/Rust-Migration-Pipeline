"""Runs the real pipeline in the Docker sandbox with a scripted fake LLM. Skipped when the sandbox image is missing."""

import subprocess

import pytest

from app.analysis.project import build_project
from app.config import settings
from app.pipeline import prompts, runner


def _image_ready() -> bool:
    try:
        r = subprocess.run(["docker", "image", "inspect", settings.sandbox_image], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _image_ready(), reason="sandbox image not built")

PROGRAM = """import sys
n = int(sys.stdin.read())
if n < 0:
    print("neg", n // 2)
else:
    print("pos", n * 2)
"""

WRONG = """use std::io::Read;
fn main() {
    let mut s = String::new();
    std::io::stdin().read_to_string(&mut s).unwrap();
    let n: i64 = s.trim().parse().unwrap();
    if n < 0 { println!("neg {}", n / 2); } else { println!("pos {}", n * 2); }
}
"""
RIGHT = WRONG.replace("n / 2", "n.div_euclid(2)")


async def test_pipeline_repairs_floor_division(monkeypatch):
    calls = {"fix": 0}

    async def fake_chat(messages, usage=None, temperature=0.2, variant=0, cheap=False):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system == prompts.TESTS_SYSTEM:
            return '["4\\n", "-7\\n", "0\\n", "-1\\n"]'
        if system == prompts.TARGETED_SYSTEM:
            return "[]"
        if "output differs" in user:
            calls["fix"] += 1
            calls["minimized"] = user
            return f"```rust\n// file: src/main.rs\n{RIGHT}```"
        if "clippy" in user:
            return "no changes"
        return f"```rust\n{WRONG}```"

    monkeypatch.setattr(runner, "chat", fake_chat)
    events = []

    async def emit(stage, status, data):
        events.append((stage, status))

    res = await runner.run_migration(build_project({"main.py": PROGRAM}), {}, emit)
    assert res["status"] == "equivalent", res["message"]
    assert calls["fix"] == 1
    ev = res["evidence"]
    assert ev["tests_passed"] == ev["tests_total"] >= 4
    assert ev["line_coverage"] == 1.0
    assert res["quality"]["unsafe"] == 0
    assert ("verify", "failed") in events and events[-1] == ("done", "equivalent")
    assert "div_euclid" in res["files"]["src/main.rs"]


async def test_original_compile_error_is_reported(monkeypatch):
    async def fake_chat(*a, **k):
        raise AssertionError("LLM must not be called when the original does not build")

    monkeypatch.setattr(runner, "chat", fake_chat)

    async def emit(*a):
        pass

    res = await runner.run_migration(build_project({"main.cpp": "int main() { return x; }\n"}), {}, emit)
    assert res["status"] == "failed" and "does not compile" in res["message"]


UNIT_PROGRAM = """import sys


def add(a, b):
    return a + b


def floordiv(a, b):
    return a // b


def main():
    n = int(sys.stdin.read())
    print(add(n, 1))


if __name__ == "__main__":
    main()
"""

UNIT_MAIN_RS = """use std::io::Read;

fn add(a: i64, b: i64) -> i64 { a + b }
fn floordiv(a: i64, b: i64) -> i64 { a / b }

fn main() {
    let mut s = String::new();
    std::io::stdin().read_to_string(&mut s).unwrap();
    let n: i64 = s.trim().parse().unwrap();
    println!("{}", add(n, 1));
}
"""

PY_HARNESS = """import sys
from main import add, floordiv

for line in sys.stdin:
    p = line.split()
    if not p:
        continue
    try:
        if p[0] == "add":
            print(add(int(p[1]), int(p[2])))
        elif p[0] == "floordiv":
            print(floordiv(int(p[1]), int(p[2])))
        else:
            print("?")
    except Exception:
        print("error")
"""

RUST_HARNESS = """use std::io::Read;

pub fn run() {
    let mut s = String::new();
    std::io::stdin().read_to_string(&mut s).unwrap();
    for line in s.lines() {
        let p: Vec<&str> = line.split_whitespace().collect();
        if p.is_empty() { continue; }
        match p[0] {
            "add" => println!("{}", crate::add(p[1].parse().unwrap(), p[2].parse().unwrap())),
            "floordiv" => println!("{}", crate::floordiv(p[1].parse().unwrap(), p[2].parse().unwrap())),
            _ => println!("?"),
        }
    }
}
"""


async def test_function_level_check_finds_a_bug_the_program_run_never_exercises(monkeypatch):
    async def fake_chat(messages, usage=None, temperature=0.2, variant=0, cheap=False):
        system, user = messages[0]["content"], messages[-1]["content"]
        if system == prompts.TESTS_SYSTEM:
            return '["4\\n", "-7\\n", "0\\n"]'
        if system == prompts.TARGETED_SYSTEM:
            return "[]"
        if system == prompts.HARNESS_SYSTEM:
            return f"```python\n{PY_HARNESS}```"
        if system == prompts.UNIT_TESTS_SYSTEM:
            return '["add 1 2\\nfloordiv 7 2\\nfloordiv -7 2\\n", "add -5 5\\nfloordiv 9 3\\n"]'
        if "test harness into Rust" in user:
            return f"```rust\n{RUST_HARNESS}```"
        if "Rust harness and the original" in user:
            return f"```rust\n// file: src/harness.rs\n{RUST_HARNESS}```"
        if "clippy" in user:
            return "no changes"
        return f"```rust\n{UNIT_MAIN_RS}```"

    monkeypatch.setattr(runner, "chat", fake_chat)
    monkeypatch.setattr("app.pipeline.unit.UnitVerifier", runner.UnitVerifier)

    async def emit(*a):
        pass

    res = await runner.run_migration(build_project({"main.py": UNIT_PROGRAM}), {}, emit)
    assert res["status"] == "equivalent", res["message"]  # the program-level behaviour matches
    unit = res["unit"]
    assert unit["status"] == "partial", unit
    assert unit["tests_total"] >= 2 and unit["tests_passed"] < unit["tests_total"]
    assert any("floordiv" in f["stdin"] for f in unit["failures"])
    assert res["confidence"] == "medium" and "differ" in " ".join(res["explanation"]["next_steps"])
    assert "src/harness.rs" not in res["files"]  # the delivered crate does not contain the harness
