# Installs every toolchain the project needs into .tools\ so cleanup is a single folder delete.
$ErrorActionPreference = "Stop"
$root  = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root ".tools"
New-Item -ItemType Directory -Force $tools | Out-Null
$ProgressPreference = "SilentlyContinue"

# uv (Python package/runtime manager)
$uvDir = Join-Path $tools "uv"
if (-not (Test-Path "$uvDir\uv.exe")) {
    $zip = Join-Path $tools "uv.zip"
    Invoke-WebRequest "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip
    Expand-Archive $zip $uvDir -Force; Remove-Item $zip
}

# Rust toolchain (GNU target ships its own linker, no Visual Studio needed)
$env:RUSTUP_HOME = Join-Path $tools "rustup"
$env:CARGO_HOME  = Join-Path $tools "cargo"
if (-not (Test-Path "$env:CARGO_HOME\bin\cargo.exe")) {
    $init = Join-Path $tools "rustup-init.exe"
    Invoke-WebRequest "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-gnu/rustup-init.exe" -OutFile $init
    & $init -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-gnu --default-toolchain stable -c clippy
    Remove-Item $init
}

# MinGW-w64 g++ (WinLibs build)
$mingw = Join-Path $tools "mingw64"
if (-not (Test-Path "$mingw\bin\g++.exe")) {
    $zip = Join-Path $tools "mingw.zip"
    $url = "https://github.com/brechtsanders/winlibs_mingw/releases/download/14.2.0posix-19.1.1-12.0.0-ucrt-r2/winlibs-x86_64-posix-seh-gcc-14.2.0-mingw-w64ucrt-12.0.0-r2.zip"
    Invoke-WebRequest $url -OutFile $zip
    Expand-Archive $zip $tools -Force; Remove-Item $zip
}

Write-Host "Tools installed in $tools"
