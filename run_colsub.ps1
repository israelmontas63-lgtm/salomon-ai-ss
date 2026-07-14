# run_colsub.ps1 — Branch de Control Autónomo (BCA) para Windows
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Port = if ($env:COLSUB_PORT) { $env:COLSUB_PORT } else { "8000" }

Write-Host "[run_colsub] Colsub BCA · raíz=$Root · puerto=$Port"

$Py = $null
if (Test-Path "$Root\.venv\Scripts\python.exe") {
  $Py = "$Root\.venv\Scripts\python.exe"
} else {
  $Py = "python"
}

& $Py -c "import watchdog" 2>$null
if ($LASTEXITCODE -ne 0) {
  & $Py -m pip install -q watchdog psutil
}

# Matar lo que escuche en :8000
Get-NetTCPConnection -LocalPort ([int]$Port) -ErrorAction SilentlyContinue |
  ForEach-Object {
    try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
  }
Start-Sleep -Milliseconds 500

$env:BCA_MODE = "1"
$env:COLSUB_PORT = "$Port"
$env:COLSUB_HOST = "0.0.0.0"
$env:TUNEL_HABILITADO = if ($env:TUNEL_HABILITADO) { $env:TUNEL_HABILITADO } else { "true" }
$env:TUNEL_AUTO = if ($env:TUNEL_AUTO) { $env:TUNEL_AUTO } else { "true" }
$env:TUNEL_SUBDOMAIN = if ($env:TUNEL_SUBDOMAIN) { $env:TUNEL_SUBDOMAIN } else { "salomon-ai" }

Write-Host "[run_colsub] host=0.0.0.0 · túnel localtunnel auto=$($env:TUNEL_AUTO) · subdomain=$($env:TUNEL_SUBDOMAIN)"
Write-Host "[run_colsub] Public URL esperada: https://$($env:TUNEL_SUBDOMAIN).loca.lt"

& $Py -m cognicion.orquesta.bca
