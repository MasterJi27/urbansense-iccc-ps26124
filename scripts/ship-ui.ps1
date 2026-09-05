$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "Packaging dashboard only (Azure Maps / OSM ICCC + /field booth)..."
& (Join-Path $root "scripts\package-dashboard.ps1")
Set-Location $root
Write-Host "Deploying existing App Service. This is azd deploy, not azd up. Typical 3-4 minutes, not an hour."
azd deploy --no-prompt
