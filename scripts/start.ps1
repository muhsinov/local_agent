$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw ".venv topilmadi. Avval .\scripts\setup.ps1 ni ishga tushiring."
}

$envPath = Join-Path $projectRoot ".env"
$hostValue = "127.0.0.1"
$portValue = "8000"

if (Test-Path $envPath) {
    foreach ($line in Get-Content $envPath) {
        if ($line -match '^\s*HOST\s*=\s*(.+)\s*$') {
            $hostValue = $matches[1].Trim()
        }
        if ($line -match '^\s*PORT\s*=\s*(.+)\s*$') {
            $portValue = $matches[1].Trim()
        }
    }
}

Set-Location $projectRoot
& $venvPython -m uvicorn app.main:app --host $hostValue --port $portValue --reload
