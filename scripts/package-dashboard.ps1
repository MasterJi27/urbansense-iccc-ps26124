$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "dashboard")
if (-not (Test-Path "node_modules")) { npm ci } else { npm install --prefer-offline --no-audit --no-fund }
npm run build
$dest = Join-Path $root "backend\static_dash"
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse "dist" $dest
