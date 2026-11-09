# Removes everything installed or built for this project: virtualenv, node_modules, builds, job data,
# the sandbox Docker image and its build cache. Source code and .env are kept.
$root = Split-Path -Parent $PSScriptRoot
foreach ($p in ".tools", "backend\.venv", "backend\data", "frontend\node_modules", "frontend\dist", "workspace",
               "backend\.pytest_cache", "backend\.ruff_cache", "sandbox\certs\extra-ca.crt") {
    $full = Join-Path $root $p
    if (Test-Path $full) { Remove-Item -Recurse -Force $full; Write-Host "removed $p" }
}
Get-ChildItem $root -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker ps -aq --filter "label=rust-migrator=1" | ForEach-Object { docker rm -f $_ | Out-Null }
    docker image rm -f rust-migrator-sandbox:2 2>$null | Out-Null
    docker builder prune -af 2>$null | Out-Null
    Write-Host "removed sandbox image and build cache"
}
Write-Host "Cleanup done."
