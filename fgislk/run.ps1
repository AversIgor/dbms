$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Linux-контейнер OpenSSL не проходит TLS к fgislk.gov.ru. Как mirror: curl.exe / Schannel.
if (-not $env:FGIS_TLS) {
    $env:FGIS_TLS = "schannel"
}
$env:POSTGRES_HOST = "127.0.0.1"
if (-not $env:MIGRATE_URL) {
    $env:MIGRATE_URL = "http://127.0.0.1:8080"
}

python -m pip install -q -e .\fgislk
python -m fgislk serve
