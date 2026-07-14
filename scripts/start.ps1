$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw ".venv topilmadi. Avval .\scripts\setup.ps1 ni ishga tushiring."
}

Set-Location $projectRoot
& $venvPython -c "from app.config import get_settings; settings = get_settings(); print(settings.host); print(settings.port)" | ForEach-Object -Begin { $values = @() } -Process { $values += $_ } -End {
    $script:hostValue = if ($values.Count -ge 1 -and $values[0]) { $values[0] } else { "127.0.0.1" }
    $script:portValue = if ($values.Count -ge 2 -and $values[1]) { $values[1] } else { "8000" }
}

& $venvPython -m uvicorn app.main:app --host $hostValue --port $portValue --reload
