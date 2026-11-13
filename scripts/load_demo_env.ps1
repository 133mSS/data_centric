# Load local project credentials without printing their values.
# Demo traffic uses baomatdulieu_demo; POSTGRES_DB remains the app DB used by
# existing tools and by docker-compose initialization.
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
if ($env:POSTGRES_DB -ne "baomatdulieu") { throw "POSTGRES_DB phai giu la baomatdulieu; Demo su dung DEMO_DB_NAME rieng." }
if (-not $env:DEMO_DB_NAME) { $env:DEMO_DB_NAME = "baomatdulieu_demo" }
if ($env:DEMO_DB_NAME -ne "baomatdulieu_demo") { throw "DEMO_DB_NAME phai la baomatdulieu_demo." }
if (-not $env:BENCHMARK_DB_NAME) { $env:BENCHMARK_DB_NAME = "baomatdulieu_benchmark" }
if ($env:BENCHMARK_DB_NAME -ne "baomatdulieu_benchmark") { throw "BENCHMARK_DB_NAME phai la baomatdulieu_benchmark." }
if ($env:SECRET_KEY.Length -lt 32) { throw "SECRET_KEY phai co toi thieu 32 bytes." }
Write-Host "Da nap cau hinh Demo va Benchmark. Gia tri bi mat khong duoc in ra."
