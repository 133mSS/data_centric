
# Load project environment variables from .env
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $EnvFile)) {
    throw "Khong tim thay file .env tai: $EnvFile"
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()

    if (-not $line -or $line.StartsWith("#")) {
        return
    }

    if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $name = $Matches[1]
        $value = $Matches[2].Trim()

        # Remove matching surrounding quotes only
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable(
            $name, $value, "Process"
        )
    }
}

# Ask for demo password without displaying it or saving it to disk.
$securePassword = Read-Host `
    "Nhap SEED_DEMO_PASSWORD (khong hien ky tu)" `
    -AsSecureString

$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
    $securePassword
)

try {
    $demoPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:SEED_DEMO_PASSWORD = $demoPassword
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $demoPassword = $null
    $securePassword.Dispose()
}

# Validate required settings without printing secret values.
$required = @(
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "SECRET_KEY",
    "SEED_DEMO_PASSWORD"
)

$missing = @(
    $required | Where-Object {
        -not [Environment]::GetEnvironmentVariable($_, "Process")
    }
)

if ($missing.Count -gt 0) {
    throw "Thieu bien cau hinh: $($missing -join ', ')"
}

Write-Host "Da nap cau hinh lab. Khong in gia tri bi mat."
