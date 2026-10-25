# Rust Migration Pipeline

Translates C++ and Python programs to Rust through a web UI. A translation is marked **verified** only if the
Rust compiles and produces the same output as the original program on generated test inputs.

Pipeline: parse → (wrap function-only input in a driver) → generate tests and record reference output from the
real original → translate with an LLM → `cargo build` / fix loop → compare outputs → report.

LLM: Groq (`openai/gpt-oss-120b`) with Ollama (`llama3.2`) as fallback.

See [PLAN.md](PLAN.md) for the design.

## Setup (Windows)

1. `copy .env.example .env` and fill in `GROQ_API_KEY`, `ADMIN_PASSWORD`, `SESSION_SECRET`.
2. `powershell -File scripts/setup-tools.ps1` installs uv, Rust (GNU) and MinGW g++ into `.tools/`.
3. Backend: `uv sync --project backend`, then from `backend/`:
   `.venv\Scripts\python -m uvicorn app.main:app --port 8280`
4. Frontend: `cd frontend && npm install && npm run dev` (http://localhost:5280, proxies `/api` to port 8280).
5. Benchmark: `PYTHONPATH=backend backend\.venv\Scripts\python backend\scripts\benchmark.py`

`scripts/cleanup-tools.ps1` removes every downloaded tool and build artifact.

## Status

Working: Python and C++ single-file translation, live progress UI, file upload, job history (SQLite),
Cargo project download, benchmark view.
Not built yet: multi-file/zip codebase mode, Dockerfile, automated tests.
