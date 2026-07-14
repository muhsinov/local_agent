$ErrorActionPreference = "Stop"

function Get-TargetModel {
    param (
        [string]$ProjectRoot,
        [string]$PythonPath
    )

    Set-Location $ProjectRoot
    $model = & $PythonPath -c "from app.config import get_settings; print(get_settings().ollama_model)"
    if (-not $model) {
        return "qwen3:1.7b"
    }
    return $model.Trim()
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama topilmadi. Rasmiy Ollama ilovasini o‘rnating: https://ollama.com/download"
}

$targetModel = if (Test-Path $venvPython) {
    Get-TargetModel -ProjectRoot $projectRoot -PythonPath $venvPython
} else {
    "qwen3:1.7b"
}

try {
    ollama list | Out-Null
} catch {
    throw "Ollama command mavjud, lekin server ishlamayapti. Avval Ollama ilovasini ishga tushiring."
}

$models = ollama list
if ($models -match [Regex]::Escape($targetModel)) {
    Write-Host "$targetModel allaqachon mavjud."
    exit 0
}

$confirmation = Read-Host "$targetModel modeli topilmadi. Yuklab olishni xohlaysizmi? (y/N)"
if ($confirmation -notin @("y", "Y", "yes", "YES")) {
    Write-Host "Hech qanday o‘zgarish qilinmadi."
    exit 0
}

ollama pull $targetModel
