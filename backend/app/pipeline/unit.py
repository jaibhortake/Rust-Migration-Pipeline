"""Function-level verification.

The whole-program check compares one program's stdout. This stage calls individual functions and methods instead:
an LLM writes a harness in the ORIGINAL language that reads "call lines" from stdin (`name arg arg ...`) and prints one
result line per call. The same harness is translated to Rust (`src/harness.rs`, built in a throwaway copy of the crate,
so the delivered crate is untouched) and both are run on the same generated and mutated call sequences, with coverage
measured on the original. Anything that goes wrong here is reported as "skipped" with a reason; it never fails the job.
"""

import json
import random
import re
import shutil

from app.analysis.project import CPP_SOURCES
from app.config import settings
from app.llm.client import LLMError
from app.pipeline import prompts
from app.sandbox import RunResult
from app.verify.coverage import Coverage, parse_coveragepy, parse_gcov_dir
from app.verify.fuzz import mutations

HARNESS_CRATE = "migrated_h"
MAX_UNIT_CASES = 25


def skipped(reason: str) -> dict:
    return {
        "status": "skipped",
        "reason": reason,
        "functions": [],
        "tests_total": 0,
        "tests_passed": 0,
        "line_coverage": None,
        "coverage_gain": None,
        "failures": [],
    }


def callables(assessment: dict) -> list[str]:
    """Names a harness could call: free functions and class methods, minus main and private helpers."""
    out: list[str] = []
    for sym in assessment["symbols"].values():
        for f in sym["functions"]:
            name = f["name"].split("::")[-1]
            if name in ("main", "__init__") or (name.startswith("_") and not f.get("owner")) or name.startswith("~"):
                continue
            if name.startswith("operator") or (name.startswith("__") and name.endswith("__")):
                continue
            label = f"{f['owner']}.{name}" if f.get("owner") else name
            if label not in out:
                out.append(label)
    return out[:40]


def harness_main(main_rs: str, mods: list[str]) -> str:
    """The crate's main.rs with its `main` renamed (kept, unused) and a new `main` that runs the harness."""
    renamed = re.sub(r"\bfn\s+main\s*\(", "#[allow(dead_code)]\nfn migrator_original_main(", main_rs, count=1)
    header = "#![allow(dead_code, unused_imports, unused_variables)]\n"
    # imported lazily to avoid a circular import with runner.py
    from app.pipeline.runner import with_mods

    return with_mods(header + renamed, sorted({*mods, "harness"})) + "\nfn main() {\n    harness::run();\n}\n"


class UnitVerifier:
    def __init__(self, migration):
        self.m = migration
        self.sb = migration.sb
        self.lang = migration.project.language
        self.d = migration.d
        self.harness_src = ""
        self.cases: list[dict] = []
        self.cov = Coverage()
        self.objs: list[str] = []

    # ------------------------------------------------------------ entry
    async def run(self) -> dict:
        try:
            return await self._run()
        except LLMError as e:
            return skipped(f"LLM unavailable: {str(e)[:120]}")
        except Exception as e:  # never fail the job because of the optional stage
            return skipped(f"could not run: {type(e).__name__}: {str(e)[:120]}")

    async def _run(self) -> dict:
        m = self.m
        names = callables(m.assessment)
        if not names:
            return skipped("no functions or classes to call directly")
        if self.lang == "python" and "__main__" not in "\n".join(m.project.files[f] for f in m.entry_files if f in m.project.files):
            return skipped("the entry file runs its code on import (no `if __name__ == '__main__'` guard)")
        await m.emit("unit", "running", {"phase": "writing a harness for the original", "functions": names})
        if not await self._make_original_harness(names):
            return skipped("the generated harness for the original did not build")
        await m.emit("unit", "running", {"phase": "recording the original's results"})
        if not await self._record_cases():
            return skipped("the harness produced no usable output on any generated call sequence")
        await m.emit("unit", "running", {"phase": "translating the harness to Rust", "cases": len(self.cases)})
        ok, rust_h = await self._make_rust_harness()
        if not ok:
            return skipped(f"the Rust harness could not be built: {rust_h[:160]}")
        passed, failures = await self._compare()
        for _ in range(2):  # the harness translation itself may be what differs
            if not failures:
                break
            await m.emit("unit", "running", {"phase": "repairing the Rust harness", "passed": passed, "total": len(self.cases)})
            if not await self._repair_mismatch(failures[0]):
                break
            passed, failures = await self._compare()
        gain = self._gain()
        await m.emit("unit", "ok" if not failures else "failed", {"passed": passed, "total": len(self.cases)})
        return {
            "status": "equivalent" if not failures else "partial",
            "reason": "",
            "functions": names,
            "tests_total": len(self.cases),
            "tests_passed": passed,
            "line_coverage": round(self.cov.line_rate, 3) if self.cov.all_lines else None,
            "coverage_gain": gain,
            "failures": failures[:3],
        }

    def _gain(self) -> float | None:
        base = self.m.total_cov
        if not base.all_lines or not self.cov.all_lines:
            return None
        universe = base.all_lines | self.cov.all_lines
        extra = (self.cov.lines | base.lines) - base.lines
        return round(len(extra) / len(universe), 3) if universe else None

    # ------------------------------------------------------------ original harness
    async def _make_original_harness(self, names: list[str]) -> bool:
        m = self.m
        listing = m._source_listing()
        entry_rel = next((f for f in m.entry_files if f.endswith(CPP_SOURCES)), m.entry_files[0])
        if self.lang == "cpp":
            rules = prompts.HARNESS_CPP_RULES.format(entry=entry_rel)
        else:
            mods = [f[:-3].replace("/", ".") for f in m.project.files if f.endswith(".py")]
            entry_mod = entry_rel[:-3].replace("/", ".")
            rules = prompts.HARNESS_PY_RULES.format(modules=", ".join(mods), entry_module=entry_mod)
        user = f"Language: {self.lang}\nCallables found: {', '.join(names)}\n{rules}\n\nProgram:\n{listing}"
        err = ""
        for attempt in range(2):
            text = await m.ask(
                prompts.HARNESS_SYSTEM, user + (f"\n\nYour previous harness failed:\n{err[-1500:]}" if err else ""), variant=attempt
            )
            from app.pipeline.runner import extract_block

            code = extract_block(text, r"cpp|c\+\+|python|py")
            err = await self._build_original_harness(code, entry_rel)
            if not err:
                return True
        return False

    async def _build_original_harness(self, code: str, entry_rel: str) -> str:
        """Writes and builds the original-side harness. Returns '' on success or the error text."""
        m = self.m
        orig = self.d / "orig"
        if self.lang == "python":
            self.harness_src = code
            (orig / "migrator_harness.py").write_text(code, encoding="utf-8", newline="\n")
            r = await self.sb.run(["python3", "-m", "py_compile", "migrator_harness.py"], "orig")
            return "" if r.ok else r.stderr
        code = "\n".join(ln for ln in code.splitlines() if not re.match(rf'\s*#\s*include\s*"{re.escape(entry_rel)}"', ln))
        full = f'#define main original_main\n#include "{entry_rel}"\n#undef main\n{code}\n'
        self.harness_src = code
        (orig / "migrator_harness.cpp").write_text(full, encoding="utf-8", newline="\n")
        entry_files = (
            set(m.assessment["graph"]["units"][m.assessment["graph"]["entry"]]["files"]) if m.assessment["graph"]["entry"] else set()
        )
        others = [s for s in m.project.files if s.endswith(CPP_SOURCES) and s not in entry_files and s != entry_rel]
        base = getattr(m, "cpp_base", ["g++", "-std=c++20", "-I", "."])
        r = await self.sb.run(
            [*base, "-O0", "--coverage", "-c", "migrator_harness.cpp", "-o", "obj/migrator_harness.o"],
            "orig",
            timeout=settings.build_timeout_s,
        )
        if not r.ok:
            return r.stderr
        self.objs = ["obj/migrator_harness.o"] + ["obj/" + s.replace("/", "__").rsplit(".", 1)[0] + ".o" for s in others]
        r = await self.sb.run(["g++", "--coverage", *self.objs, "-o", "h_cov"], "orig", timeout=settings.build_timeout_s)
        return "" if r.ok else r.stderr

    async def _run_h(self, stdin: str) -> tuple[RunResult, Coverage | None]:
        files = set(self.m.project.files)
        if self.lang == "cpp":
            obj = self.d / "orig" / "obj"
            for g in [*obj.glob("*.gcda"), *obj.glob("*.gcov.json.gz")]:
                g.unlink(missing_ok=True)
            r = await self.sb.run(["./h_cov"], "orig", stdin)
            if not r.ok:
                return r, None
            await self.sb.run(["gcov", "-b", "--json-format", *(o.split("/")[-1] for o in self.objs)], "orig/obj")
            return r, parse_gcov_dir(obj, files)
        js = self.d / "cov" / "h.json"
        js.unlink(missing_ok=True)
        r = await self.sb.run(
            ["python3", "-m", "coverage", "run", "--branch", f"--data-file={self.sb.scratch}/hdata", "migrator_harness.py"], "orig", stdin
        )
        if not r.ok:
            return r, None
        await self.sb.run(
            ["python3", "-m", "coverage", "json", f"--data-file={self.sb.scratch}/hdata", "-o", "../cov/h.json", "-q"], "orig"
        )
        return r, parse_coveragepy(js, files)

    async def _record_cases(self) -> bool:
        m = self.m
        text = await m.ask(prompts.UNIT_TESTS_SYSTEM, f"Harness ({self.lang}):\n{self.harness_src[:12000]}")
        seeds: list[str] = []
        mm = re.search(r"\[.*\]", text, re.S)
        if mm:
            try:
                seeds = [x if isinstance(x, str) else json.dumps(x) for x in json.loads(mm.group(0))][:10]
            except json.JSONDecodeError:
                seeds = []
        for s in seeds:
            await self._try(s, "llm", False)
        if not self.cases:
            return False
        rng = random.Random(4321)
        pool = [c["stdin"] for c in self.cases]
        i = 0
        while len(self.cases) < MAX_UNIT_CASES and i < len(pool) * 3 and i < 30:
            for mut in mutations(pool[i % len(pool)], rng, 2):
                if await self._try(mut, "mutation", True):
                    pool.append(mut)
            i += 1
        return True

    async def _try(self, stdin: str, origin: str, need_new: bool) -> bool:
        if any(c["stdin"] == stdin for c in self.cases) or len(self.cases) >= MAX_UNIT_CASES:
            return False
        r, cov = await self._run_h(stdin)
        if not r.ok or not r.stdout.strip():
            return False
        if cov is not None and need_new and not cov.adds_to(self.cov):
            return False
        if cov is not None:
            self.cov.merge(cov)
        self.cases.append({"stdin": stdin, "expected": r.stdout, "origin": origin})
        return True

    # ------------------------------------------------------------ Rust harness
    def _api(self) -> str:
        from app.pipeline.runner import public_api

        parts = []
        for path, code in self.m.rust.items():
            if path == "src/harness.rs":
                continue
            api = public_api(code, 80)
            if path == "src/main.rs":
                # items at the crate root are reachable by a child module even when private
                items = [
                    ln.strip().rstrip("{").strip()
                    for ln in code.splitlines()
                    if re.match(r"\s*(pub\s+)?(fn|struct|enum|trait|impl|type|const)\b", ln) and "fn main" not in ln
                ]
                api = "\n".join(items[:120])
            parts.append(f"{'crate (main.rs)' if path == 'src/main.rs' else 'mod ' + path[4:-3]}:\n{api}")
        return "\n\n".join(parts)[:14000]

    async def _make_rust_harness(self) -> tuple[bool, str]:
        m = self.m
        from app.pipeline.runner import extract_block

        text = await m.ask(
            prompts.TRANSLATE_SYSTEM.format(lang=m._lang),
            prompts.RUST_HARNESS_TASK.format(lang=self.lang, api=self._api(), harness=self.harness_src[:12000]),
        )
        self.rust_harness = extract_block(text)
        err = ""
        for attempt in range(4):
            self._write_rust_h()
            r = await m._cargo("build", "rust_h")
            if r.ok:
                return True, ""
            err = r.stderr
            if attempt == 3:
                break
            fix = await m.ask(
                prompts.TRANSLATE_SYSTEM.format(lang=m._lang),
                f"Current src/harness.rs:\n```rust\n{self.rust_harness}```\n\nCrate API:\n{self._api()}\n\n"
                + prompts.FIX_HARNESS.format(errors=err[-4000:]),
            )
            from app.pipeline.runner import extract_files

            new = extract_files(fix, "src/harness.rs").get("src/harness.rs")
            if new:
                self.rust_harness = new
        return False, err.strip().splitlines()[0] if err.strip() else "build failed"

    def _write_rust_h(self) -> None:
        h = self.d / "rust_h"
        if h.exists():
            shutil.rmtree(h)
        (h / "src").mkdir(parents=True)
        cargo = (self.d / "rust" / "Cargo.toml").read_text(encoding="utf-8").replace('name = "migrated"', f'name = "{HARNESS_CRATE}"')
        (h / "Cargo.toml").write_text(cargo, encoding="utf-8")
        mods = [p[4:-3] for p in self.m.rust if p not in ("src/main.rs", "src/harness.rs")]
        for p, t in self.m.rust.items():
            if p == "src/main.rs":
                t = harness_main(t, mods)
            if p != "src/harness.rs":
                (h / p).write_text(t, encoding="utf-8", newline="\n")
        (h / "src" / "harness.rs").write_text(self.rust_harness, encoding="utf-8", newline="\n")

    async def _compare(self) -> tuple[int, list[dict]]:
        from app.pipeline.runner import compare

        passed = 0
        failures: list[dict] = []
        for c in self.cases:
            r = await self.sb.run([self.sb.rust_exe(HARNESS_CRATE)], "rust_h", c["stdin"])
            actual = r.stdout if r.ok else ("(timed out)" if r.timed_out else r.stdout + f"\n[exit {r.returncode}] {r.stderr[-300:]}")
            if r.ok and compare(c["expected"], r.stdout) != "diff":
                passed += 1
            else:
                failures.append({"stdin": c["stdin"][:1500], "expected": c["expected"][:1500], "actual": actual[:1500]})
        return passed, failures

    async def _repair_mismatch(self, failure: dict) -> bool:
        from app.pipeline.runner import extract_files

        m = self.m
        fix = await m.ask(
            prompts.TRANSLATE_SYSTEM.format(lang=m._lang),
            f"Original harness:\n```\n{self.harness_src[:8000]}```\n\nCurrent src/harness.rs:\n```rust\n{self.rust_harness}```\n\n"
            + prompts.FIX_HARNESS_MISMATCH.format(stdin=failure["stdin"], expected=failure["expected"], actual=failure["actual"]),
        )
        new = extract_files(fix, "src/harness.rs").get("src/harness.rs")
        if not new or new == self.rust_harness:
            return False
        previous = self.rust_harness
        self.rust_harness = new
        self._write_rust_h()
        if not (await m._cargo("build", "rust_h")).ok:
            self.rust_harness = previous
            self._write_rust_h()
            await m._cargo("build", "rust_h")
            return False
        return True
