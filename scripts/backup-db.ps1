# Copy the local database. Postgres uses pg_dump. SQLite copies the file.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$dest = Join-Path $root "storage\backups"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$url = $env:DATABASE_URL
if (-not $url) { $url = "sqlite:///$root/backend/urbansense.db" }
if ($url -like "sqlite:*") {
  $path = $url -replace "^sqlite:///?", ""
  if (-not [System.IO.Path]::IsPathRooted($path)) { $path = Join-Path $root $path }
  if (-not (Test-Path $path)) { throw "SQLite file not found: $path" }
  Copy-Item $path (Join-Path $dest "urbansense-$stamp.db")
  Write-Host "Copied $path"
} else {
  $out = Join-Path $dest "urbansense-$stamp.sql"
  & pg_dump $url -f $out
  Write-Host "Wrote $out"
}
