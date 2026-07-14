# start_salomon_movil.ps1 — Servidor 0.0.0.0 + localtunnel (Public URL)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Port = if ($env:COLSUB_PORT) { $env:COLSUB_PORT } else { "8000" }

Write-Host "[móvil] Liberando :$Port y arrancando Colsub + localtunnel…"
& "$Root\run_colsub.ps1"
