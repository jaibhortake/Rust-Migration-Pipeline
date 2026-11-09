# Rust Migrator

An **analysis-first** pipeline that migrates C++ and Python codebases (single files or multi-file projects) to Rust,
and backs every result with **measured evidence** instead of "the LLM said so".

Any LLM can turn a file of C++ into something that looks like Rust. Real migrations fail on other problems:
- inconsistent decisions across files;
- semantic traps such as Python's `//` floor division, dict insertion order, unbounded ints, or inheritance hierarchies;
- not knowing whether the result *behaves* the same.

This project is built around those problems.

## What it does

| Stage | What happens | LLM? |
|---|---|---|
| **1. Assessment** | tree-sitter symbol tables, file/module dependency graph (SCCs, leaves-first order), cyclomatic complexity, risk detector for ~35 semantic hazards with a Rust strategy for each, per-module difficulty, effort estimate, readiness verdict | no (instant, free) |
| **2. Mapping contract** | **Class map** (struct / trait / implementor / enum / composition / error enum, with the reason and the trait impls each dunder/operator needs), **library map** (header/module → std, allowed crate, manual, unsupported), **type map**. All editable in the UI; the same contract is given to every module so all files make the same decisions. | no |
| **3. Coverage-guided test generation** | Inputs come from LLM seeds, then **mutation fuzzing**, then **LLM prompts that target the exact lines not yet executed**. Each input runs on the *real original*, instrumented with gcov or coverage.py. Inputs whose output is not deterministic are dropped. | yes |
| **4. Module-by-module translation** | Leaves first. Each module gets the contract plus the public API of modules already migrated. Each dependency group must pass `cargo check` (with compiler-guided repair) before the next group starts. | yes |
| **5. Differential verification** | The whole crate is built and run on every recorded input. Failing inputs are **shrunk with delta debugging** before the repair prompt. | yes (repairs) |
| **6. Quality** | clippy and rustfmt. A clippy clean-up is kept **only if every test still passes**. Scores count `unsafe`, unwrap/clone density and Rc/RefCell use. | yes (once) |
| **6b. Function-level checks** | After the program-level check passes, an LLM writes a harness in the original language that calls individual functions and methods from stdin "call lines". The same harness is translated to Rust (built in a throwaway copy of the crate) and both are run on generated and mutated call sequences, with coverage. Catches bugs a whole-program run never reaches, and works for libraries with no `main`. | yes |
| **7. Report** | Status, confidence, line and branch coverage, minimised failures, side-by-side diff. The download includes `MIGRATION_REPORT.md` and the recorded tests as a **`cargo test` regression suite**. | no |

### Also built in
- **Programs that read no input** are detected: test generation is skipped, the single deterministic run is compared once, and the UI says so.
- **Qwen for cheap steps**: seed test-input generation goes to a local Ollama model when available (about 15 tokens/s on a 4 GB laptop GPU), and falls back to Groq if it is missing or slow. Set `CHEAP_LLM=groq` to turn it off.
- **Truncated model replies are continued** automatically (large modules exceed the output limit).
- **Parallel translation**: independent modules translate at the same time; each dependency wave must compile before the next.
- **Resume**: a failed or interrupted migration keeps a checkpoint (recorded tests, compiled modules); "Resume from checkpoint" continues from there.
- **requirements.txt / CMakeLists.txt** are read: declared Python packages are mapped (and unsupported ones flagged) up front; CMake selects the executable target, sources, include dirs and C++ standard.
- **Old-toolchain tolerance**: C++ that relies on headers newer standard libraries include implicitly (for example `<utility>`) is retried with common headers force-included.
- **Report extras**: plain-language explanation of every outcome, a check of which class/library decisions the translator actually followed, and a report-only download (`/api/jobs/<id>/report`).

### What "equivalent" means (and does not mean)
The status is **"behaviourally equivalent on N tests"**: the Rust program printed exactly what the original printed
for every recorded input. This is **test-based behavioural verification, not a proof of equivalence**. Behaviour on
untested inputs, and on lines the tests never executed, is unverified. That is why every report shows the original's
line and branch coverage and lists the never-executed lines for manual review. Confidence:
- *high*: all tests pass and ≥ 90% line coverage with ≥ 8 inputs
- *medium*: ≥ 70% line coverage
- *low*: less coverage than that

Floats are compared with a 1e-9 relative tolerance, and every such match is counted separately.

### Security: the sandbox
Uploaded code and generated Rust are compiled and run **only inside Docker containers** built from `sandbox/Dockerfile`:
- `--network none`
- memory, CPU and pids limits
- `--cap-drop ALL`, `no-new-privileges`
- non-root user, tmpfs scratch space
- a per-command `timeout` plus a host-side kill
- one container per job, removed afterwards; leftovers are removed when the server starts

Crates allowed in generated code (`num-bigint`, `regex`, `serde_json`, `itertools`, …) are fetched when the image is built, and jobs build with `--offline`.
`SANDBOX=local` exists for development without Docker and gives **no isolation**.

Other hardening:
- signed session cookies that expire (`httponly`, `samesite=strict`, optional `secure`)
- rate-limited login with constant-time password comparison
- the server refuses to start with an empty password or a weak secret
- upload size and file-count limits
- zip-slip and zip-bomb checks
- an allowlist for crates
- no shell interpolation anywhere

## Quick start (Windows)

Requires [uv](https://docs.astral.sh/uv/), Node.js 20+, and Docker Desktop (running).

```powershell
powershell -File scripts\setup.ps1   # .env, Python deps, frontend build, sandbox image (~1.5 GB)
# edit .env: GROQ_API_KEY, ADMIN_PASSWORD, SESSION_SECRET (16+ random chars)
powershell -File scripts\start.ps1   # http://127.0.0.1:8280
```

Development with hot reload: run `uvicorn app.main:app --port 8280` in `backend/`, then `npm run dev` in `frontend/`
(http://localhost:5280, which proxies `/api` to the backend).

If your antivirus or proxy re-signs TLS (for example Norton Web Shield), export its root CA to `sandbox/certs/extra-ca.crt`
before building the image.

`scripts\cleanup-tools.ps1` removes the virtualenv, node_modules, builds, job data, the sandbox image and the Docker build cache.

## Tests and benchmark

```powershell
cd backend
uv run pytest -q                 # unit + API tests; Docker integration tests run when the sandbox image exists
uv run ruff check app tests scripts
uv run python -m scripts.benchmark   # full pipeline vs one-shot LLM baseline on samples/ (calls the LLM)
```

The integration tests drive the real sandbox with a scripted fake LLM: a deliberately wrong translation must be
caught, minimised and repaired. CI (`.github/workflows/ci.yml`) runs lint, all tests and the frontend build.

The benchmark covers 30 programs (single files and multi-file projects, including a C++20 stress test). It scores the full
pipeline and a one-shot "just ask the LLM" baseline on **the same recorded inputs**, and can switch one feature off at a time:

```powershell
uv run python -m scripts.benchmark --configs full,baseline,no-contract,no-targeting,no-minimize,no-repair,no-unit
```

Results (pass rate, coverage, quality, LLM calls, per-feature contribution) appear on the Benchmark page. A full run with all
configurations is hours of LLM time on a free Groq tier; start with `--limit 5`.

## Layout

```
backend/app/
  analysis/   project loading, tree-sitter symbols, dependency graph, risk rules, assessment
  mapping/    class, library and type mapping (the migration contract)
  verify/     coverage parsers (gcov / coverage.py), mutation + delta debugging, clippy/quality scoring
  pipeline/   orchestration (runner.py), prompts, markdown report
  sandbox.py  Docker / local execution     security.py  sessions, rate limit     db.py  SQLite
frontend/src/ pages: New → Assessment → Mappings → Migrate (live) → Report; Benchmark
sandbox/      Dockerfile for the execution sandbox (+ prefetched crates)
samples/      single-file programs and multi-file projects
```

## Limits
- Programs must be deterministic stdin/stdout programs to be verified. File, network and GUI I/O and randomness are flagged as unsupported.
- One language per project. The Rust output is one crate: one module per Python file, or per C++ header/source pair.
- Templates, macros, and pointer-heavy data structures get a strategy, but expect review.
- The effort estimate is a heuristic (about 30 LOC per hour, scaled by risk), not a measured figure.
