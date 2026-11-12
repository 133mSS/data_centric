$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Chua tim thay .venv. Tao moi bang: python -m venv .venv"
}

. ".\.venv\Scripts\Activate.ps1"
. ".\scripts\load_demo_env.ps1"
python .\demo_server.py
