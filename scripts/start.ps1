param(
    [string]$Python = 'python',
    [int]$Port = 8050
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot 'src'
if (-not $env:new_apikey) {
    $env:new_apikey = [Environment]::GetEnvironmentVariable('new_apikey', 'User')
}
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
& $Python -X utf8 -m retrieval_mcp --port $Port
