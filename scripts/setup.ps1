$ErrorActionPreference = "Stop"

function Get-PythonCandidate {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $version = [Version](& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
        if ($version -ge [Version]"3.11.0") {
            return @{
                Command = "python"
                Version = $version
                Arguments = @()
            }
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $version = [Version](& py -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
            return @{
                Command = "py"
                Version = $version
                Arguments = @("-3.11")
            }
        } catch {
        }
    }

    throw "Python 3.11 yoki undan yangi interpreter topilmadi."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidate = Get-PythonCandidate

Set-Location $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonCandidate.Command @($pythonCandidate.Arguments + @("-m", "venv", ".venv"))
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "data", "data/uploads", "data/vector_store" | Out-Null

Write-Host "Setup tugadi."
Write-Host "Ishga tushirish: .\scripts\start.ps1"
