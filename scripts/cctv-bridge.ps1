param(
  [Parameter(Mandatory = $true)][string]$SnapshotUrl,
  [string]$Api = "https://app-urbansense-yngmbk.azurewebsites.net",
  [string]$Token = $env:URBANSENSE_TOKEN,
  [string]$Code = "CAM-DVR-01",
  [string]$Bay = "FRONT",
  [string]$Vendor = "HTTP_SNAPSHOT",
  [string]$Bus = "BUS-042",
  [string]$Kind = "BUS_CCTV"
)
$ErrorActionPreference = "Stop"
if (-not $Token) { throw "Set URBANSENSE_TOKEN or pass -Token. This script runs on the PC next to the DVR — UrbanSense ships no camera box." }
$tmp = Join-Path $env:TEMP ("urbansense-" + $Code + ".jpg")
Write-Host "Pulling one JPEG (not RTSP video) from the DVR..."
Invoke-WebRequest -Uri $SnapshotUrl -OutFile $tmp -TimeoutSec 12
$headers = @{ Authorization = "Bearer $Token" }
$form = @{
  file = Get-Item $tmp
  source_id = $Code
  bus_id = $Bus
  camera_bay = $Bay
  vendor = $Vendor
  source_kind = $Kind
  latitude = "28.6328"
  longitude = "77.2195"
}
$res = Invoke-RestMethod -Method Post -Uri ($Api.TrimEnd("/") + "/ingest/cctv/still") -Headers $headers -Form $form
Write-Host ("Ingested " + $res.event.public_code + " · " + $res.event.event_type)
