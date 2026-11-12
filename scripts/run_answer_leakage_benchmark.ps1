$ErrorActionPreference = 'Stop'

# Run from the repository root after loading .env via scripts/load_lab_env.ps1.
$tokenLines = & python .\experiments\common\issue_benchmark_tokens.py
if ($LASTEXITCODE -ne 0) {
    throw 'Token issuance failed. Benchmark was not started; see the error above.'
}
if (-not $tokenLines) {
    throw 'Token issuer returned no token assignments. Benchmark was not started.'
}
foreach ($line in $tokenLines) {
    if ($line -match '^\$env:RAG_BENCH_TOKEN_[A-Z0-9_]+\s*=') {
        Invoke-Expression $line
    }
}

$required = @(
    'RAG_BENCH_TOKEN_NV_DEV',
    'RAG_BENCH_TOKEN_MGR_TECH',
    'RAG_BENCH_TOKEN_MGR_SALES',
    'RAG_BENCH_TOKEN_PARTNER_01',
    'RAG_BENCH_TOKEN_CEO_BOSS'
)
$missing = @($required | Where-Object { -not (Get-Item "Env:$($_)" -ErrorAction SilentlyContinue) })
if ($missing.Count -gt 0) {
    throw "Missing benchmark token(s): $($missing -join ', '). Benchmark was not started."
}

Write-Host 'All 5 benchmark tokens are present. Starting answer-level leakage benchmark...'
& python .\experiments\answer_leakage\answer_leakage_test_public_entrypoints.py
if ($LASTEXITCODE -ne 0) {
    throw 'Answer-level leakage benchmark failed. Review the error above.'
}
