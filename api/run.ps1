$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:POSTGRES_HOST = "127.0.0.1"
if (-not $env:MIGRATE_URL) {
    $env:MIGRATE_URL = "http://127.0.0.1:8080"
}

python -m pip install -q -e .\api
python -m api serve
