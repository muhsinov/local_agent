$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }

    throw "Python topilmadi. Python 3.11 yoki undan yangi versiyani o‘rnating."
}

function Get-PythonVersion {
    param (
        [string]$PythonCommand
    )

    if ($PythonCommand -eq "py") {
        return [Version](& py -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
    }

    return [Version](& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCommand = Get-PythonCommand
$pythonVersion = Get-PythonVersion -PythonCommand $pythonCommand

if ($pythonVersion -lt [Version]"3.11.0") {
    throw "Python 3.11 yoki undan yangi versiya kerak. Topilgan: $pythonVersion"
}

Set-Location $projectRoot

& $pythonCommand -m venv .venv

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "data", "data/uploads", "data/vector_store" | Out-Null

Write-Host "Setup tugadi."
Write-Host "Ishga tushirish: .\scripts\start.ps1"
