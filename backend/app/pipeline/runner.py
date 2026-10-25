import json
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.config import ROOT, settings
from app.llm.client import LLMError, chat
from app.pipeline import prompts
from app.pipeline.parse import parse
from app.toolchain import run

Emit = Callable[[str, str, dict], Awaitable[None]]

WORKSPACE = ROOT / "workspace"
CARGO_TOML = '[package]\nname = "migrated"\nversion = "0.1.0"\nedition = "2021"\n\n[profile.release]\nopt-level = 1\n'


@dataclass
class JobResult:
    status: str = "failed"  # verified | compiles_only | failed
    rust: str = ""
    original: str = ""
    attempts: int = 0
    unsafe_count: int = 0
    providers: set[str] = field(default_factory=set)
    message: str = ""
    tests_passed: int = 0
    tests_total: int = 0
    seconds: float = 0.0
    failures: list[dict] = field(default_factory=list)  # up to 3 failing cases from the last verify run


def _extract_block(text: str, lang: str) -> str:
    m = re.search(rf"```(?:{lang})?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


async def _ask(system: str, user: str, result: JobResult, history: list[dict] | None = None) -> str:
    messages = [{"role": "system", "content": system}] + (history or []) + [{"role": "user", "content": user}]
    text, provider = await chat(messages)
    result.providers.add(provider)
    return text


async def _build_original(language: str, code: str, d: Path) -> tuple[list[str] | None, str]:
    if language == "python":
        (d / "orig.py").write_text(code, encoding="utf-8")
        return [sys.executable, "-I", str(d / "orig.py")], ""
    (d / "orig.cpp").write_text(code, encoding="utf-8")
    r = await run(["g++", "-O1", "-std=c++17", "orig.cpp", "-o", "orig.exe"], d, settings.build_timeout_s)
    if r.returncode != 0:
        return None, r.stderr
    return [str(d / "orig.exe")], ""


async def run_job(language: str, code: str, emit: Emit) -> JobResult:
    t0 = time.monotonic()
    res = JobResult(original=code)
    WORKSPACE.mkdir(exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(dir=WORKSPACE))
    try:
        await _pipeline(language, code, emit, res, job_dir)
    except LLMError as e:
        res.status, res.message = "failed", f"LLM unavailable: {e}"
    except Exception as e:  # keep the job record intact for the UI
        res.status, res.message = "failed", f"internal error: {e}"
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
    res.seconds = round(time.monotonic() - t0, 1)
    await emit("done", res.status, {"message": res.message})
    return res


async def _pipeline(language: str, code: str, emit: Emit, res: JobResult, d: Path) -> None:
    # 1. parse
    await emit("parse", "running", {})
    p = parse(language, code)
    if not p.ok:
        await emit("parse", "failed", {"errors": p.errors})
        res.message = "; ".join(p.errors)
        return
    await emit("parse", "ok", {"functions": p.functions, "warnings": p.warnings, "full_program": p.has_entrypoint})

    # 2. make it a full program if it's only a function
    program = code
    if not p.has_entrypoint:
        await emit("analyze", "running", {"note": "function-only input, generating driver"})
        usable = False
        for _ in range(3):  # models sometimes return a broken or incomplete driver
            text = await _ask(prompts.DRIVER_SYSTEM, f"Language: {language}\n\n{code}", res)
            program = _extract_block(text, "python|cpp|c\\+\\+")
            again = parse(language, program)
            if again.ok and again.has_entrypoint:
                usable = True
                break
        if not usable:
            await emit("analyze", "failed", {})
            res.message = "could not build a runnable driver for the function"
            return
    res.original = program
    await emit("analyze", "ok", {})

    # 3. reference outputs from the REAL original program
    await emit("tests", "running", {})
    cmd, err = await _build_original(language, program, d)
    if cmd is None:
        await emit("tests", "failed", {"errors": err[:1500]})
        res.message = "original C++ does not compile"
        return
    cases: list[tuple[str, str]] = []
    for _ in range(3):  # retry when the model's inputs are unparseable or the program rejects all of them
        text = await _ask(prompts.TESTS_SYSTEM, f"Program ({language}):\n{program}", res)
        try:
            inputs = json.loads(re.search(r"\[.*\]", text, re.S).group(0))  # type: ignore[union-attr]
            inputs = [str(i) for i in inputs][:10]
        except (AttributeError, json.JSONDecodeError):
            continue
        for stdin in inputs:
            r = await run(cmd, d, settings.run_timeout_s, stdin)
            if r.returncode == 0 and not r.timed_out:
                cases.append((stdin, r.stdout))
        if cases:
            break
    if not cases:
        await emit("tests", "failed", {})
        res.message = "no usable test inputs (original failed on all generated inputs)"
        return
    res.tests_total = len(cases)
    await emit("tests", "ok", {"count": len(cases)})

    # 4. translate
    await emit("translate", "running", {})
    src = d / "rust" / "src"
    src.mkdir(parents=True)
    (d / "rust" / "Cargo.toml").write_text(CARGO_TOML)
    system = prompts.TRANSLATE_SYSTEM.format(lang="C++" if language == "cpp" else "Python")
    history: list[dict] = []
    user = f"Translate this {language} program to Rust:\n\n{program}"
    text = await _ask(system, user, res)
    history += [{"role": "user", "content": user}, {"role": "assistant", "content": text}]
    rust = _extract_block(text, "rust")
    await emit("translate", "ok", {})

    # 5+6. compile-fix and verify loop
    budget = settings.max_compile_attempts + settings.max_verify_attempts
    exe = d / "rust" / "target" / "release" / "migrated.exe"
    compiled = False
    for attempt in range(1, budget + 1):
        res.attempts = attempt
        (src / "main.rs").write_text(rust, encoding="utf-8")
        await emit("compile", "running", {"attempt": attempt})
        b = await run(["cargo", "build", "--release", "--quiet"], d / "rust", settings.build_timeout_s)
        if b.returncode != 0 and re.search(r"linking with|ld\.exe|cannot find -l|link\.exe", b.stderr):
            # Environment problem, not the model's fault: don't burn attempts asking it to "fix" a linker.
            await emit("compile", "failed", {"attempt": attempt, "errors": b.stderr[-1500:]})
            res.message = "toolchain/linker error (check .tools setup)"
            res.rust = rust
            return
        if b.returncode != 0:
            await emit("compile", "failed", {"attempt": attempt, "errors": b.stderr[-1500:]})
            fix = prompts.FIX_COMPILE.format(errors=b.stderr[-4000:])
        else:
            compiled = True
            res.rust = rust
            await emit("compile", "ok", {"attempt": attempt})
            await emit("verify", "running", {"attempt": attempt})
            fix = None
            passed = 0
            res.failures = []
            for stdin, expected in cases:
                r = await run([str(exe)], d, settings.run_timeout_s, stdin)
                if not r.timed_out and r.returncode == 0 and _norm(r.stdout) == _norm(expected):
                    passed += 1
                    continue
                if len(res.failures) < 3:
                    res.failures.append({
                        "stdin": stdin[:500],
                        "expected": expected[:500],
                        "actual": ("(timed out)" if r.timed_out else (r.stdout or r.stderr))[:500],
                    })
                if fix is None:
                    fix = prompts.FIX_MISMATCH.format(
                        stdin=stdin[:1000], expected=expected[:1000], actual=(r.stdout or r.stderr)[:1000]
                    )
            res.tests_passed = passed
            await emit("verify", "ok" if passed == len(cases) else "failed", {"passed": passed, "total": len(cases)})
            if passed == len(cases):
                res.status = "verified"
                break
        if attempt == budget:
            break
        text = await _ask(system, fix, res, history)  # type: ignore[arg-type]
        history += [{"role": "user", "content": fix}, {"role": "assistant", "content": text}]
        history = history[-6:]
        new_rust = _extract_block(text, "rust")
        if "fn main" in new_rust:  # ignore empty/truncated replies and keep the last real attempt
            rust = new_rust

    if res.status != "verified":
        res.status = "compiles_only" if compiled else "failed"
        res.message = "output mismatch after retries" if compiled else "did not compile within retry budget"
    res.rust = res.rust or rust
    res.unsafe_count = len(re.findall(r"\bunsafe\b", res.rust))
    await emit("report", "ok", {"unsafe": res.unsafe_count, "attempts": res.attempts})
