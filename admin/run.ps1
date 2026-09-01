$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $env:MIGRATE_URL) {
    $env:MIGRATE_URL = "http://127.0.0.1:8080"
}
if (-not $env:FGISLK_URL) {
    $env:FGISLK_URL = "http://127.0.0.1:8081"
}

python -m pip install -q -e .\admin
python -m admin serve
