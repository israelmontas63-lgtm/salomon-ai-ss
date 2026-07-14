# keep_tunnel.ps1 — Conexión permanente localtunnel (subdominio fijo)
$ErrorActionPreference = "Continue"
$Port = if ($env:COLSUB_PORT) { $env:COLSUB_PORT } else { "8000" }
$Sub = if ($env:TUNEL_SUBDOMAIN) { $env:TUNEL_SUBDOMAIN } else { "salomon-ai" }

Write-Host "[túnel] Conexión permanente → https://$Sub.loca.lt (puerto $Port)"
Write-Host "[túnel] Reinicio automático si el proceso cae. Ctrl+C para detener."

while ($true) {
  Write-Host "[túnel] Arrancando npx localtunnel --port $Port --subdomain $Sub …"
  npx --yes localtunnel --port $Port --subdomain $Sub
  $code = $LASTEXITCODE
  Write-Host "[túnel] Proceso terminó (código $code). Reintentando en 3s…"
  Start-Sleep -Seconds 3
}
