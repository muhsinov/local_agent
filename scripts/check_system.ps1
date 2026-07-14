$ErrorActionPreference = "Stop"

$pythonInfo = if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -0p 2>$null
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python --version 2>$null
} else {
    "Python topilmadi"
}

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name
$ramBytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$ramGb = [Math]::Round($ramBytes / 1GB, 2)
$gpu = (Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$freeGb = [Math]::Round($disk.FreeSpace / 1GB, 2)
$ollamaInstalled = if (Get-Command ollama -ErrorAction SilentlyContinue) { "o‘rnatilgan" } else { "o‘rnatilmagan" }

Write-Host "Python: $pythonInfo"
Write-Host "CPU: $cpu"
Write-Host "RAM: $ramGb GB"
Write-Host "GPU: $gpu"
Write-Host "C disk bo‘sh joy: $freeGb GB"
Write-Host "Ollama: $ollamaInstalled"
