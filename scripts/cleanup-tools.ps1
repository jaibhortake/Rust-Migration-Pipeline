# Removes every downloaded tool and build artifact. Run after the code is pushed to git.
$root = Split-Path -Parent $PSScriptRoot
foreach ($p in ".tools", "backend\.venv", "frontend\node_modules", "frontend\dist", "workspace") {
    $full = Join-Path $root $p
    if (Test-Path $full) { Remove-Item -Recurse -Force $full; Write-Host "removed $p" }
}
Get-ChildItem $root -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
# Pre-existing rustup install (user asked for it to be removed too)
$cargo = Join-Path $env:USERPROFILE ".cargo"
$rustup = Join-Path $env:USERPROFILE ".rustup"
foreach ($p in $cargo, $rustup) { if (Test-Path $p) { Remove-Item -Recurse -Force $p; Write-Host "removed $p" } }
# The uv cache for this project lives in .tools\uv-cache (removed above); the global uv and npm caches
# are shared with other projects, so they are left alone.
Write-Host "Cleanup done."
