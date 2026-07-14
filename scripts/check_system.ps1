$ErrorActionPreference = "Stop"

function Get-SafeValue {
    param (
        [scriptblock]$Script,
        [string]$Fallback
    )

    try {
        $result = & $Script
        if ($null -eq $result -or [string]::IsNullOrWhiteSpace([string]$result)) {
            return $Fallback
        }
        return $result
    } catch {
        return $Fallback
    }
}

$pythonInfo = Get-SafeValue -Fallback "Python topilmadi" -Script {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python --version 2>$null
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -0p 2>$null
    }
}

$cpu = Get-SafeValue -Fallback "Aniqlanmadi" -Script {
    Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name
}

$ramGb = Get-SafeValue -Fallback "Aniqlanmadi" -Script {
    $ramBytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    "{0} GB" -f [Math]::Round($ramBytes / 1GB, 2)
}

$gpuNames = Get-SafeValue -Fallback @() -Script {
    @(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)
}

$diskFree = Get-SafeValue -Fallback "Aniqlanmadi" -Script {
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    "{0} GB" -f [Math]::Round($disk.FreeSpace / 1GB, 2)
}

$ollamaInstalled = if (Get-Command ollama -ErrorAction SilentlyContinue) { "o'rnatilgan" } else { "o'rnatilmagan" }
$nvidia = @($gpuNames | Where-Object { $_ -match "NVIDIA" })
$intel = @($gpuNames | Where-Object { $_ -match "Intel" })
$otherGpu = @($gpuNames | Where-Object { $_ -and $_ -notmatch "NVIDIA|Intel" })

Write-Host "Python: $pythonInfo"
Write-Host "CPU: $cpu"
Write-Host "RAM: $ramGb"
Write-Host "NVIDIA GPU: $([string]::Join('; ', $nvidia))"
Write-Host "Intel GPU: $([string]::Join('; ', $intel))"
Write-Host "Other GPU: $([string]::Join('; ', $otherGpu))"
Write-Host "C disk bo'sh joy: $diskFree"
Write-Host "Ollama: $ollamaInstalled"
