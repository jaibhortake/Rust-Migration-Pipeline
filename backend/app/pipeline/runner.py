"""Migration pipeline.

prepare -> build original (plain + coverage-instrumented) -> coverage-guided differential test generation
-> module-by-module translation in dependency order (each module compile-gated) -> whole-crate build/verify/fix loop
with delta-debugged failing inputs -> clippy-driven refinement gated by the tests -> report.

"Equivalent" in the result means: identical stdout on every recorded test input. That is test-based behavioural
evidence, quantified by the line/branch coverage those inputs reach in the original program. It is not a proof.
"""

import asyncio
import json
import posixpath
import random
import re
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.analysis.assess import analyze
from app.analysis.graph import module_name
from app.analysis.project import CPP_SOURCES, Project
from app.config import ROOT, settings
from app.llm.client import LLMError, Usage, chat
from app.mapping.libraries import crates_for
from app.pipeline import prompts
from app.sandbox import RunResult, Sandbox, SandboxError, make_sandbox
from app.verify.coverage import Coverage, parse_coveragepy, parse_gcov_dir
from app.verify.fuzz import minimize, mutations
from app.verify.quality import parse_clippy, score

Emit = Callable[[str, str, dict], Awaitable[None]]
WORKSPACE = ROOT / "workspace"
MAX_SOURCE_CHARS = 40_000


def cargo_toml(deps: list[str]) -> str:
    return (
        '[package]\nname = "migrated"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
        + "".join(d + "\n" for d in deps)
        + "\n[profile.release]\nopt-level = 2\n"
    )


# ------------------------------------------------------------------ helpers (pure, unit-tested)


def extract_block(text: str, lang: str = "rust") -> str:
    m = re.search(rf"```(?:{lang})?[ \t]*\n(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip() + "\n"


def extract_files(text: str, default: str | None = None) -> dict[str, str]:
    """```rust blocks whose first line is `// file: src/x.rs`. A single unlabeled block goes to `default`."""
    out: dict[str, str] = {}
    blocks = re.findall(r"```(?:rust|rs)?[ \t]*\n(.*?)```", text, re.DOTALL)
    for b in blocks:
        m = re.match(r"\s*//\s*file:\s*(\S+)\s*\n", b)
        if m:
            path = m.group(1).lstrip("./")
            if re.fullmatch(r"src/[\w/]+\.rs", path):
                out[path] = b[m.end() :].strip() + "\n"
        elif len(blocks) == 1 and default:
            out[default] = b.strip() + "\n"
    return out


def norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


_FLOAT = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?|-?\d+[eE][-+]?\d+")


def compare(expected: str, actual: str) -> str:
    """'exact', 'numeric' (same text except floats within 1e-9 relative), or 'diff'."""
    e, a = norm(expected), norm(actual)
    if e == a:
        return "exact"
    if _FLOAT.sub("#", e) != _FLOAT.sub("#", a):
        return "diff"
    for x, y in zip(_FLOAT.findall(e), _FLOAT.findall(a), strict=True):
        fx, fy = float(x), float(y)
        if abs(fx - fy) > 1e-9 * max(1.0, abs(fx), abs(fy)):
            return "diff"
    return "numeric"


def public_api(rust: str, limit: int = 60) -> str:
    keep = []
    for line in rust.splitlines():
        s = line.strip()
        if re.match(r"(pub(\(crate\))?\s+(fn|struct|enum|trait|type|const|static)\b|impl\b|#\[derive)", s):
            keep.append(re.sub(r"\s*\{\s*$", "", s).rstrip(";"))
        if len(keep) >= limit:
            break
    return "\n".join(keep)


def with_mods(main_rs: str, mods: list[str]) -> str:
    body = (
        "\n".join(ln for ln in main_rs.splitlines() if not re.match(rf"\s*(pub\s+)?mod\s+({'|'.join(map(re.escape, mods))})\s*;", ln))
        if mods
        else main_rs
    )
    lines = body.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("#![") or not lines[i].strip() or lines[i].startswith("//!")):
        i += 1
    header = [f"mod {m};" for m in mods]
    return "\n".join(lines[:i] + header + lines[i:]) + "\n"


def parse_json_list(text: str) -> list[str] | None:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [x if isinstance(x, str) else json.dumps(x) if not isinstance(x, (int, float)) else str(x) for x in data]


# ------------------------------------------------------------------ pipeline


class Migration:
    def __init__(self, project: Project, mappings: dict, emit: Emit, job_dir: Path, sandbox: Sandbox):
        self.project, self.mappings, self.emit = project, mappings, emit
        self.d, self.sb = job_dir, sandbox
        self.usage = Usage()
        self.assessment: dict = {}
        self.cases: list[dict] = []  # {stdin, expected, origin}
        self.total_cov = Coverage()
        self.flaky = 0
        self.rust: dict[str, str] = {}  # "src/x.rs" -> code
        self.modules: list[dict] = []
        self.failures: list[dict] = []
        self.counters = {"module_fixes": 0, "verify_rounds": 0, "refine_accepted": False}
        self.result: dict = {"status": "failed", "message": ""}

    # ---- LLM
    async def ask(self, system: str, user: str, history: list[dict] | None = None, variant: int = 0) -> str:
        msgs = [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": user}]
        return await chat(msgs, self.usage, variant=variant)

    # ---- stage 0: function-only input gets a driver
    async def prepare(self) -> bool:
        await self.emit("prepare", "running", {})
        self.assessment, suggested = analyze(self.project)
        s = self.assessment["summary"]
        if s["blockers"]:
            await self.emit("prepare", "failed", {"errors": s["blockers"]})
            self.result["message"] = "; ".join(s["blockers"])
            return False
        if s["single_function"]:
            path, code = next(iter(self.project.files.items()))
            original_names = {f["name"] for f in self.assessment["symbols"][path]["functions"]} | {
                c["name"] for c in self.assessment["symbols"][path]["classes"]
            }
            for attempt in range(3):
                text = await self.ask(prompts.DRIVER_SYSTEM, f"Language: {self.project.language}\n\n{code}", variant=attempt)
                program = extract_block(text, r"python|py|cpp|c\+\+")
                trial = Project(self.project.language, {path: program})
                a, _ = analyze(trial)
                kept = {f["name"] for f in a["symbols"][path]["functions"]} | {c["name"] for c in a["symbols"][path]["classes"]}
                if not a["summary"]["blockers"] and not a["summary"]["single_function"] and original_names <= kept:
                    self.project, self.assessment = trial, a
                    break
            else:
                await self.emit("prepare", "failed", {"errors": ["could not build a runnable driver for the function"]})
                self.result["message"] = "could not build a runnable driver for the function"
                return False
            await self.emit("prepare", "ok", {"note": "function-only input: generated a stdin/stdout driver"})
        else:
            await self.emit("prepare", "ok", {"units": len(self.assessment["units"])})
        if not self.mappings:
            self.mappings = suggested
        return True

    # ---- stage 1: original program
    async def build_original(self) -> bool:
        await self.emit("build_original", "running", {})
        orig = self.d / "orig"
        for p, t in self.project.files.items():
            f = orig / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t, encoding="utf-8", newline="\n")
        (self.d / "cov").mkdir()
        if self.project.language == "cpp":
            (orig / "obj").mkdir()
            sources = [p for p in self.project.files if p.endswith(CPP_SOURCES)]
            self.objs = []
            for s in sources:
                obj = "obj/" + s.replace("/", "__").rsplit(".", 1)[0] + ".o"
                r = await self.sb.run(
                    ["g++", "-std=c++20", "-O0", "--coverage", "-I", ".", "-c", s, "-o", obj], "orig", timeout=settings.build_timeout_s
                )
                if not r.ok:
                    return await self._orig_fail(r)
                self.objs.append(obj)
            r = await self.sb.run(["g++", "--coverage", *self.objs, "-o", "cov_bin"], "orig", timeout=settings.build_timeout_s)
            if not r.ok:
                return await self._orig_fail(r)
            r = await self.sb.run(
                ["g++", "-std=c++20", "-O2", "-I", ".", *sources, "-o", "plain_bin"], "orig", timeout=settings.build_timeout_s
            )
            if not r.ok:
                return await self._orig_fail(r)
        entry = self.assessment["graph"]["entry"]
        units = self.assessment["graph"]["units"]
        self.entry_files = units[entry]["files"] if entry else list(self.project.files)
        await self.emit("build_original", "ok", {})
        return True

    async def _orig_fail(self, r: RunResult) -> bool:
        await self.emit("build_original", "failed", {"errors": r.stderr[-2000:]})
        self.result["message"] = "the original C++ does not compile"
        return False

    async def run_original(self, stdin: str, coverage: bool) -> tuple[RunResult, Coverage | None]:
        files = set(self.project.files)
        if self.project.language == "cpp":
            if not coverage:
                return await self.sb.run(["./plain_bin"], "orig", stdin), None
            obj = self.d / "orig" / "obj"
            for g in [*obj.glob("*.gcda"), *obj.glob("*.gcov.json.gz")]:
                g.unlink(missing_ok=True)
            r = await self.sb.run(["./cov_bin"], "orig", stdin)
            if not r.ok:
                return r, None
            await self.sb.run(["gcov", "-b", "--json-format", *(o.split("/")[-1] for o in self.objs)], "orig/obj")
            return r, parse_gcov_dir(obj, files)
        entry = self.entry_files[0]
        if not coverage:
            return await self.sb.run(["python3", entry], "orig", stdin), None
        js = self.d / "cov" / "c.json"
        js.unlink(missing_ok=True)
        r = await self.sb.run(
            ["python3", "-m", "coverage", "run", "--branch", f"--data-file={self.sb.scratch}/covdata", entry], "orig", stdin
        )
        if not r.ok:
            return r, None
        await self.sb.run(
            ["python3", "-m", "coverage", "json", f"--data-file={self.sb.scratch}/covdata", "-o", "../cov/c.json", "-q"], "orig"
        )
        return r, parse_coveragepy(js, files)

    # ---- stage 2: coverage-guided differential test generation
    def _source_listing(self, mark: dict[str, list[int]] | None = None) -> str:
        parts = []
        for p, t in self.project.files.items():
            marked = set((mark or {}).get(p, []))
            body = "\n".join((">> " if i in marked else "   ") + ln for i, ln in enumerate(t.splitlines(), 1)) if mark is not None else t
            parts.append(f"// ===== {p}\n{body}")
        return "\n\n".join(parts)[:MAX_SOURCE_CHARS]

    async def _try_input(self, stdin: str, origin: str, require_new: bool, runs: list[int]) -> bool:
        if any(c["stdin"] == stdin for c in self.cases) or len(self.cases) >= settings.max_tests:
            return False
        runs[0] += 1
        r, cov = await self.run_original(stdin, coverage=True)
        if not r.ok:
            return False
        if cov is not None and require_new and not cov.adds_to(self.total_cov):
            return False
        if cov is not None:
            self.total_cov.merge(cov)
        self.cases.append({"stdin": stdin, "expected": r.stdout, "origin": origin})
        return True

    async def generate_tests(self) -> bool:
        await self.emit("tests", "running", {"phase": "seed inputs"})
        runs = [0]
        listing = self._source_listing()
        for attempt in range(3):
            text = await self.ask(prompts.TESTS_SYSTEM, f"Program ({self.project.language}):\n{listing}", variant=attempt)
            inputs = parse_json_list(text) or []
            for s in inputs[:14]:
                await self._try_input(s, "llm", False, runs)
            if self.cases:
                break
        if not self.cases:
            await self.emit("tests", "failed", {"errors": "the original program rejected every generated input"})
            self.result["message"] = "no usable test inputs (the original failed on all generated inputs)"
            return False
        await self.emit("tests", "running", {"phase": "mutation", "line_coverage": round(self.total_cov.line_rate, 3)})

        rng = random.Random(1234)
        seeds = [c["stdin"] for c in self.cases]
        i = 0
        while runs[0] < settings.exploration_runs and len(self.cases) < settings.max_tests and seeds:
            if self.total_cov.line_rate >= 0.999 and (self.total_cov.branch_rate or 1) >= 0.999:
                break
            seed = seeds[i % len(seeds)]
            i += 1
            for m in mutations(seed, rng, 3):
                if await self._try_input(m, "mutation", True, runs):
                    seeds.append(m)
            if i > len(seeds) * 3:
                break

        for rnd in range(settings.targeted_rounds):
            if self.total_cov.line_rate >= settings.coverage_target or len(self.cases) >= settings.max_tests:
                break
            await self.emit(
                "tests",
                "running",
                {"phase": f"targeting uncovered code (round {rnd + 1})", "line_coverage": round(self.total_cov.line_rate, 3)},
            )
            examples = json.dumps([c["stdin"] for c in self.cases[:4]])
            text = await self.ask(
                prompts.TARGETED_SYSTEM,
                f"Example valid inputs: {examples}\n\nProgram:\n" + self._source_listing(self.total_cov.uncovered()),
                variant=rnd,
            )
            for s in (parse_json_list(text) or [])[:6]:
                await self._try_input(s, "targeted", True, runs)

        # determinism check and reference outputs from the uninstrumented (optimised) original
        kept = []
        self.orig_seconds = 0.0
        for c in self.cases:
            r, _ = await self.run_original(c["stdin"], coverage=False)
            if not r.ok or norm(r.stdout) != norm(c["expected"]):
                self.flaky += 1
                continue
            self.orig_seconds += r.seconds
            kept.append(c)
        self.cases = kept
        if not self.cases:
            await self.emit("tests", "failed", {"errors": "outputs are not deterministic"})
            self.result["message"] = "the original program's output is not deterministic"
            return False
        if not any(norm(c["expected"]) for c in self.cases):
            await self.emit("tests", "failed", {"errors": "the original program prints nothing on any input"})
            self.result["message"] = (
                "the original program prints nothing on every input, so there is nothing to compare: equivalence cannot be checked"
            )
            return False
        await self.emit(
            "tests",
            "ok",
            {
                "count": len(self.cases),
                "line_coverage": round(self.total_cov.line_rate, 3),
                "branch_coverage": None if self.total_cov.branch_rate is None else round(self.total_cov.branch_rate, 3),
                "flaky_dropped": self.flaky,
            },
        )
        return True

    # ---- stage 3: module-by-module translation
    def _contract(self, unit: dict, done: list[str]) -> str:
        files = set(unit["files"])
        m = self.mappings
        lines = ["Migration contract (follow it):"]
        types = m.get("types", [])
        if types:
            lines.append("Type mapping:")
            lines += [f"- {t['source']} -> {t['target']}" + (f" ({t['note']})" if t.get("note") else "") for t in types]
        libs = [x for x in m.get("libraries", []) if not x.get("used_in") or files & set(x["used_in"])]
        if libs:
            lines.append("Library mapping:")
            lines += [f"- {x['source']} -> {x['target']} [{x['kind']}]" + (f" ({x['note']})" if x.get("note") else "") for x in libs]
        classes = [c for c in m.get("classes", []) if c["file"] in files]
        if classes:
            lines.append("Class mapping (Rust has no inheritance):")
            for c in classes:
                s = f"- {c['name']}: {c['target']}. {c['rationale']}"
                if c.get("trait_impls"):
                    s += f" Implement: {', '.join(c['trait_impls'])}."
                if c.get("notes"):
                    s += f" Reviewer note: {c['notes']}"
                lines.append(s)
        others = [c for c in m.get("classes", []) if c["file"] not in files]
        if others:
            lines.append("Types defined in other modules: " + "; ".join(f"{c['name']} = {c['target']}" for c in others))
        risks = [r for r in self.assessment.get("risks", []) if r["file"] in files]
        if risks:
            lines.append("Known semantic hazards in this module (apply the strategy):")
            lines += [f"- line {r['line']}: {r['title']}: {r['strategy']}" for r in risks]
        if done:
            lines.append("Already migrated modules (public API you must use, do not redefine):")
            for uid in done:
                path = f"src/{uid}.rs"
                if path in self.rust:
                    lines.append(f"mod {uid}:\n{public_api(self.rust[path])}")
        return "\n".join(lines)

    async def _cargo(self, sub: str) -> RunResult:
        cmd = ["cargo", sub, "--release", "--quiet", "--color", "never"]
        if self.sb.name == "docker":
            cmd.append("--offline")
        return await self.sb.run(cmd, "rust", timeout=settings.build_timeout_s)

    def _write_rust(self) -> None:
        src = self.d / "rust" / "src"
        if src.exists():
            shutil.rmtree(src)
        src.mkdir(parents=True)
        for p, t in self.rust.items():
            (self.d / "rust" / p).write_text(t, encoding="utf-8", newline="\n")

    def _assemble(self, partial: bool) -> None:
        mods = sorted(p[4:-3] for p in self.rust if p != "src/main.rs")
        if partial or "src/main.rs" not in self.rust:
            self.rust["src/main.rs"] = "#![allow(dead_code, unused_imports)]\nfn main() {}\n"
        self.rust["src/main.rs"] = with_mods(self.rust["src/main.rs"], mods)

    async def _compile_fix(self, label: str, default_path: str, attempts: int, check: bool) -> tuple[bool, RunResult]:
        r = RunResult(1, "", "")
        history: list[dict] = []
        for attempt in range(attempts + 1):
            self._write_rust()
            r = await self._cargo("check" if check else "build")
            if r.ok:
                return True, r
            if re.search(r"linker|ld returned|cannot find -l|failed to select a version|no matching package", r.stderr):
                return False, r  # environment problem: asking the model to "fix" it wastes calls
            if attempt == attempts:
                break
            self.counters["module_fixes"] += 1
            await self.emit(
                "compile" if label == "crate" else "translate",
                "running",
                {"module": label, "fix_attempt": attempt + 1, "errors": r.stderr[-1200:]},
            )
            user = prompts.FIX_COMPILE.format(errors=r.stderr[-5000:])
            ctx = "\n\n".join(f"```rust\n// file: {p}\n{t}```" for p, t in self.rust.items() if p == default_path or p == "src/main.rs")
            text = await self.ask(prompts.TRANSLATE_SYSTEM.format(lang=self._lang), ctx + "\n\n" + user, history)
            history = (history + [{"role": "user", "content": user}, {"role": "assistant", "content": text}])[-4:]
            for p, t in extract_files(text, default_path).items():
                if p == "src/main.rs" and default_path != "src/main.rs" and "fn main() {}" in self.rust.get(p, ""):
                    continue  # the placeholder main is ours
                self.rust[p] = t
            self._assemble(partial=default_path != "src/main.rs")
        return False, r

    @property
    def _lang(self) -> str:
        return "C++" if self.project.language == "cpp" else "Python"

    async def translate(self) -> bool:
        g = self.assessment["graph"]
        units = {u["id"]: u for u in self.assessment["units"]}
        crate_deps = crates_for(self.mappings.get("libraries", []))
        (self.d / "rust").mkdir(exist_ok=True)
        (self.d / "rust" / "Cargo.toml").write_text(cargo_toml(crate_deps), encoding="utf-8")
        done: list[str] = []
        entry = g["entry"] or next(iter(units))
        order = [grp for grp in g["order"]]
        system = prompts.TRANSLATE_SYSTEM.format(lang=self._lang)
        for grp in order:
            for uid in grp:
                u = units[uid]
                is_entry = uid == entry
                target = "src/main.rs" if is_entry else f"src/{uid}.rs"
                await self.emit("translate", "running", {"module": uid, "target": target})
                source = "\n\n".join(f"// ===== {f}\n{self.project.files[f]}" for f in u["files"])[:MAX_SOURCE_CHARS]
                task = prompts.MODULE_TASK.format(
                    lang=self._lang,
                    unit=uid,
                    files=", ".join(u["files"]),
                    target=target,
                    role=prompts.ROLE_ENTRY if is_entry else prompts.ROLE_MODULE,
                    contract=self._contract(u, done),
                    source=source,
                )
                code = ""
                for attempt in range(2):
                    code = extract_block(await self.ask(system, task, variant=attempt))
                    if code.strip() and (not is_entry or "fn main" in code):
                        break
                self.rust[target] = code
                self.modules.append({"id": uid, "files": u["files"], "rust": target, "status": "translated", "fixes": 0})
            # compile gate after each dependency group (a cycle is checked as a whole)
            if all(uid != entry for uid in grp):
                before = self.counters["module_fixes"]
                self._assemble(partial=True)
                ok, r = await self._compile_fix(",".join(grp), f"src/{grp[-1]}.rs", settings.max_module_fix_attempts, check=True)
                for m in self.modules:
                    if m["id"] in grp:
                        m["status"] = "compiles" if ok else "failed"
                        m["fixes"] = self.counters["module_fixes"] - before
                if not ok:
                    await self.emit("translate", "failed", {"module": ",".join(grp), "errors": r.stderr[-2000:]})
                    self.result.update(status="compile_failed", message=f"module {','.join(grp)} does not compile")
                    return False
                await self.emit("translate", "ok", {"module": ",".join(grp)})
            done += [x for x in grp if x != entry]
        self._assemble(partial=False)
        return True

    # ---- stage 4: whole crate build + differential verification
    async def run_rust(self, stdin: str) -> RunResult:
        return await self.sb.run([self.sb.rust_exe()], "rust", stdin)

    async def verify(self) -> bool:
        history: list[dict] = []
        system = prompts.TRANSLATE_SYSTEM.format(lang=self._lang)
        rounds = settings.max_verify_attempts
        for rnd in range(rounds + 1):
            self.counters["verify_rounds"] = rnd + 1
            await self.emit("compile", "running", {"round": rnd + 1})
            ok, r = await self._compile_fix("crate", "src/main.rs", settings.max_module_fix_attempts, check=False)
            if not ok:
                await self.emit("compile", "failed", {"errors": r.stderr[-2000:]})
                self.result.update(status="compile_failed", message="the crate does not compile")
                return False
            await self.emit("compile", "ok", {"round": rnd + 1})
            await self.emit("verify", "running", {"round": rnd + 1})
            passed, numeric, first_fail, rust_s = 0, 0, None, 0.0
            self.failures = []
            for c in self.cases:
                rr = await self.run_rust(c["stdin"])
                rust_s += rr.seconds
                verdict = compare(c["expected"], rr.stdout) if rr.ok else "diff"
                if verdict != "diff":
                    passed += 1
                    numeric += verdict == "numeric"
                    continue
                actual = (
                    "(timed out)" if rr.timed_out else rr.stdout + (f"\n[exit {rr.returncode}] {rr.stderr[-300:]}" if rr.returncode else "")
                )
                if len(self.failures) < 3:
                    self.failures.append({"stdin": c["stdin"][:2000], "expected": c["expected"][:2000], "actual": actual[:2000]})
                first_fail = first_fail or c
            self.passed, self.numeric, self.rust_seconds = passed, numeric, rust_s
            await self.emit(
                "verify", "ok" if passed == len(self.cases) else "failed", {"passed": passed, "total": len(self.cases), "round": rnd + 1}
            )
            if passed == len(self.cases):
                return True
            if rnd == rounds:
                break
            # shrink the failing input so the model sees the essence of the bug
            await self.emit("verify", "running", {"phase": "minimising failing input"})

            async def still_fails(s: str) -> bool:
                o, _ = await self.run_original(s, coverage=False)
                if not o.ok:
                    return False
                rr = await self.run_rust(s)
                return not rr.ok or compare(o.stdout, rr.stdout) == "diff"

            small = await minimize(first_fail["stdin"], still_fails, budget=30)
            o, _ = await self.run_original(small, coverage=False)
            rr = await self.run_rust(small)
            self.failures[0]["minimized"] = small[:2000]
            hints = "\n".join(f"Hint: {r['title']}: {r['strategy']}" for r in self.assessment.get("risks", []) if r["severity"] != "low")[
                :2000
            ]
            user = prompts.FIX_MISMATCH.format(
                stdin=small[:2000], expected=o.stdout[:2000], actual=(rr.stdout or rr.stderr)[:2000], hints=hints
            )
            ctx = "\n\n".join(f"```rust\n// file: {p}\n{t}```" for p, t in self.rust.items())[:MAX_SOURCE_CHARS]
            try:
                text = await self.ask(system, f"Current crate:\n{ctx}\n\nOriginal program:\n{self._source_listing()}\n\n{user}", history)

            except LLMError as e:  # keep the compiled crate and the evidence
                self.result["message"] = f"repair stopped, LLM unavailable: {e}"
                return False
            history = (history + [{"role": "user", "content": user}, {"role": "assistant", "content": text}])[-4:]
            for p, t in extract_files(text, "src/main.rs").items():
                if p == "src/main.rs" and "fn main" not in t:
                    continue
                self.rust[p] = t
            self._assemble(partial=False)
        return False

    # ---- stage 5: quality, refinement gated by the tests
    async def clippy(self) -> list[dict]:
        cmd = ["cargo", "clippy", "--release", "--message-format=json", "--color", "never"]
        if self.sb.name == "docker":
            cmd.append("--offline")
        r = await self.sb.run(cmd, "rust", timeout=settings.build_timeout_s)
        return parse_clippy(r.stdout)

    async def quality(self, equivalent: bool) -> dict:
        await self.emit("quality", "running", {})
        warnings = await self.clippy()
        try:
            if equivalent and warnings:
                saved = dict(self.rust)
                listing = "\n".join(f"{w['file']}:{w['line']} {w['lint']}: {w['message']}" for w in warnings[:25])
                ctx = "\n\n".join(f"```rust\n// file: {p}\n{t}```" for p, t in self.rust.items())[:MAX_SOURCE_CHARS]
                text = await self.ask(
                    prompts.TRANSLATE_SYSTEM.format(lang=self._lang), ctx + "\n\n" + prompts.REFINE_CLIPPY.format(warnings=listing)
                )
                changed = extract_files(text)
                if changed:
                    self.rust.update(changed)
                    self._assemble(partial=False)
                    self._write_rust()
                    b = await self._cargo("build")
                    ok = b.ok
                    if ok:
                        for c in self.cases:
                            rr = await self.run_rust(c["stdin"])
                            if not rr.ok or compare(c["expected"], rr.stdout) == "diff":
                                ok = False
                                break
                    new_warnings = await self.clippy() if ok else warnings
                    if ok and len(new_warnings) < len(warnings):
                        warnings = new_warnings
                        self.counters["refine_accepted"] = True
                    else:
                        self.rust = saved
                        self._write_rust()
        except LLMError:
            pass  # refinement is optional
        fmt = await self.sb.run(["cargo", "fmt", "--", "--check"], "rust")
        changed_lines = len([ln for ln in fmt.stdout.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---")])
        await self.sb.run(["cargo", "fmt"], "rust")  # formatting cannot change behaviour
        for p in list(self.rust):
            f = self.d / "rust" / p
            if f.exists():
                self.rust[p] = f.read_text(encoding="utf-8")
        q = score(self.rust, warnings, changed_lines)
        q["rustfmt_applied"] = True
        await self.emit("quality", "ok", {"score": q["score"], "clippy": q["clippy_warnings"]})
        return q

    # ---- orchestrate
    async def run(self) -> dict:
        t0 = time.monotonic()
        self.orig_seconds = 0.0
        self.passed = self.numeric = 0
        self.rust_seconds = 0.0
        quality = None
        equivalent = False
        try:
            if not await self.prepare():
                return self._finish(t0, quality)
            await self.sb.start()
            if not await self.build_original() or not await self.generate_tests():
                return self._finish(t0, quality)
            if not await self.translate():
                return self._finish(t0, quality)
            equivalent = await self.verify()
            if self.result.get("status") != "compile_failed":
                quality = await self.quality(equivalent)
                self.result["status"] = "equivalent" if equivalent else "partial"
                if not equivalent and not self.result.get("message"):
                    self.result["message"] = f"{self.passed}/{len(self.cases)} tests match after all repair rounds"
        except LLMError as e:
            self.result.update(status="failed", message=f"LLM unavailable: {e}")
        except SandboxError as e:
            self.result.update(status="failed", message=str(e))
        except Exception as e:  # keep the job record for the UI
            self.result.update(status="failed", message=f"internal error: {type(e).__name__}: {e}")
        finally:
            await self.sb.stop()
        return self._finish(t0, quality)

    def _finish(self, t0: float, quality: dict | None) -> dict:
        lc = self.total_cov.line_rate if self.total_cov.all_lines else None
        bc = self.total_cov.branch_rate
        st = self.result["status"]
        if st == "equivalent":
            cov = lc or 0
            confidence = "high" if cov >= 0.9 and len(self.cases) >= 8 else "medium" if cov >= 0.7 else "low"
        else:
            confidence = "none"
        origins: dict[str, int] = {}
        for c in self.cases:
            origins[c["origin"]] = origins.get(c["origin"], 0) + 1
        uncovered = self.total_cov.uncovered() if self.total_cov.all_lines else {}
        speed = (self.orig_seconds / self.rust_seconds) if self.rust_seconds and self.passed else None
        self.result.update(
            {
                "confidence": confidence,
                "files": {"Cargo.toml": cargo_toml(crates_for(self.mappings.get("libraries", []))), **self.rust},
                "original_files": self.project.files,
                "modules": self.modules,
                "evidence": {
                    "tests_total": len(self.cases),
                    "tests_passed": self.passed,
                    "numeric_matches": self.numeric,
                    "line_coverage": None if lc is None else round(lc, 3),
                    "branch_coverage": None if bc is None else round(bc, 3),
                    "inputs_by_origin": origins,
                    "flaky_dropped": self.flaky,
                    "uncovered": {f: ls[:50] for f, ls in uncovered.items()},
                },
                "failures": self.failures,
                "quality": quality,
                "performance": {
                    "original_s": round(self.orig_seconds, 3),
                    "rust_s": round(self.rust_seconds, 3),
                    "ratio": round(speed, 2) if speed else None,
                    "note": "Wall time per run includes the sandbox's process start-up, which is the same "
                    "for both; small programs are dominated by it.",
                },
                "attempts": self.counters,
                "usage": self.usage.to_dict(),
                "tests": self.cases[: settings.max_tests],
                "sandbox": self.sb.name,
                "seconds": round(time.monotonic() - t0, 1),
            }
        )
        return self.result


_slots = asyncio.Semaphore(settings.max_concurrent_jobs)


async def run_migration(project: Project, mappings: dict, emit: Emit) -> dict:
    WORKSPACE.mkdir(exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(dir=WORKSPACE))
    try:
        async with _slots:
            await emit("queue", "ok", {})
            m = Migration(project, mappings, emit, job_dir, make_sandbox(job_dir))
            result = await m.run()
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
    await emit("done", result["status"], {"message": result.get("message", "")})
    return result


__all__ = ["module_name", "posixpath", "run_migration"]
