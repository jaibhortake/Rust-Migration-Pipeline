# Code-to-Rust Migration Pipeline — Plan

## Goal
A localhost web app: the user logs in, picks **C++** or **Python**, pastes or uploads code,
and watches it get translated to Rust in real time. A translation is shown as **verified**
only if it compiles and gives the same output as the original on test inputs.

## Stack (current versions)
| Layer | Choice |
|---|---|
| Frontend | React 19, Vite 7, TypeScript, Tailwind CSS v4, Monaco Editor (side-by-side diff), TanStack Query |
| Live updates | WebSocket (FastAPI native) |
| Backend | Python 3.13, FastAPI, Pydantic v2, `uv` for dependencies |
| Parsing | tree-sitter (C++, Python), Python `ast` |
| LLM | Groq `openai/gpt-oss-120b` (main), Ollama `llama3.2` (fallback when Groq fails or is rate-limited) |
| Toolchains | Rust stable (GNU), MinGW-w64 g++, all installed in `.tools/` |
| Storage | SQLite (job history, cache of LLM responses) |
| Auth | Single admin login from `.env`, signed session cookie |
| Tests | pytest (backend), Vitest (frontend), a sample corpus of LeetCode-style problems |

## Pipeline stages (each streams its status to the UI)
1. **Parse**: tree-sitter extracts functions, classes, includes and imports; rejects syntax errors early.
2. **Analyze**: maps types and constructs with a rule table (`vector`→`Vec`, `dict`→`HashMap`,
   exceptions→`Result`, …) and flags hard constructs (templates, raw pointers, `eval`, …).
3. **Generate tests**: the LLM proposes test inputs; the **original** program is run on them to record
   reference outputs. The reference comes from running the real code, never from the LLM.
4. **Translate**: the LLM gets the source, the rule table and the analysis notes, and writes a Cargo project.
5. **Compile-fix loop**: runs `cargo build` and `clippy`, feeds the errors back to the LLM, up to N attempts.
6. **Verify**: runs the Rust binary on the same inputs and compares outputs (normalized for whitespace
   and float precision). Mismatches go back to step 4, within a retry budget.
7. **Report**: status (verified / compiles-only / failed), diff view, `unsafe` count, attempts, timings, download as zip.

## Sandboxing (localhost-only, but the app still runs code it was given)
Each job runs in its own temp directory, with a timeout, an output size limit, and no shell interpolation.

## Folder layout
```
migration/
  backend/   app/{api,pipeline,llm,toolchain,models}  tests/
  frontend/  src/{pages,components,hooks}
  samples/   cpp/  python/   (LeetCode-style problems with tests)
  scripts/   setup-tools.ps1, cleanup-tools.ps1
  Dockerfile, docker-compose.yml, README.md, .env (not committed)
```

## Milestones
1. Scaffold + set up toolchains in `.tools/` + health check page
2. Pipeline for **Python→Rust** on 10 LeetCode-style samples, end to end
3. **C++→Rust** on 10 samples
4. Real-time UI: login, editor, live stage timeline, diff, history
5. Hardening: retries, caching, rate-limit handling, Groq→Ollama fallback, tests, logging
6. Multi-file / real-codebase mode (upload a zip, translate module by module in dependency order)
7. Docs + Dockerfile, then you push to git; then `cleanup-tools.ps1` removes `.tools/`, the Rust
   toolchain, `rustup`, caches and `node_modules`

## Success metric
Percentage of samples **verified** (compiles and outputs match). Shown on a benchmark page in the UI.
