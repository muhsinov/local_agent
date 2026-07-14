$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error ".venv topilmadi. Avval .\\scripts\\setup.ps1 ni ishga tushiring."
}

$env:PYTHONUTF8 = "1"
$helper = @'
from app.config import get_settings
from app.rag.embedding_model import SentenceTransformerEmbeddingModel

settings = get_settings()
model = SentenceTransformerEmbeddingModel(settings)
dimension = model.get_dimension()
vector = model.encode_query("embedding smoke test")
print(f"model={settings.embedding_model_name}")
print(f"dimension={dimension}")
print(f"vector_shape={vector.shape}")
'@

$answer = Read-Host "Model cache'da bo'lmasa yuklab olishga ruxsat berasizmi? (y/N)"
if ($answer -notin @("y", "Y", "yes", "YES")) {
    Write-Host "Bekor qilindi."
    exit 1
}

& $venvPython -c $helper
