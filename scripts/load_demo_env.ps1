# Load only the environment needed by the local demo web server.
# This intentionally does not prompt for SEED_DEMO_PASSWORD and never prints secrets.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) { throw "Khong tim thay file .env tai: $EnvFile" }

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$required = @("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "SECRET_KEY")
$missing = @($required | Where-Object { -not [Environment]::GetEnvironmentVariable($_, "Process") })
if ($missing.Count -gt 0) { throw "Thieu bien cau hinh demo: $($missing -join ', ')" }
if ($env:POSTGRES_DB -ne "baomatdulieu") { throw "DEMO chi duoc phep ket noi database baomatdulieu; hien tai POSTGRES_DB khong hop le." }
if ($env:SECRET_KEY.Length -lt 32) { throw "SECRET_KEY phai co toi thieu 32 bytes." }
Write-Host "Da nap cau hinh cho demo local. Gia tri bi mat khong duoc in ra." 
