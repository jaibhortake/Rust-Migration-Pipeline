# One-time setup on Windows: Python deps, frontend build, sandbox image.
# Requires: uv, Node.js 20+, Docker Desktop (running).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$env:UV_NATIVE_TLS = "1"   # use the Windows certificate store (works behind TLS-scanning antivirus/proxies)

if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env"; Write-Host "Created .env: fill in GROQ_API_KEY, ADMIN_PASSWORD, SESSION_SECRET" }

Push-Location "$root\backend"; uv sync; Pop-Location
Push-Location "$root\frontend"; npm install --no-audit --no-fund; npm run build; Pop-Location

# Networks that re-sign TLS (e.g. antivirus web shields) need their root CA inside the image build.
# Put such a CA as sandbox\certs\*.crt (git-ignored) before running this script.
docker build -t rust-migrator-sandbox:2 "$root\sandbox"
Write-Host "Setup done. Start with: scripts\start.ps1  (then open http://127.0.0.1:8280)"
