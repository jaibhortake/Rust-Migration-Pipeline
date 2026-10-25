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
# uv and npm caches created by this project
foreach ($p in "$env:LOCALAPPDATA\uv") { if (Test-Path $p) { Remove-Item -Recurse -Force $p; Write-Host "removed $p" } }
npm cache clean --force 2>$null
Write-Host "Cleanup done."
