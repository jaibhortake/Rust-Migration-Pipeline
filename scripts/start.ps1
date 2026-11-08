# Production-style start: the backend serves the built frontend on one port.
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
& .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8280
