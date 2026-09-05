param(
  [Parameter(Mandatory = $true)][string]$SnapshotUrl,
  [string]$Api = "https://app-urbansense-yngmbk.azurewebsites.net",
  [string]$Token = $env:URBANSENSE_TOKEN,
  [string]$Code = "CAM-DVR-01",
  [string]$Bay = "FRONT",
  [string]$Vendor = "HTTP_SNAPSHOT",
  [string]$Bus = "BUS-042",
  [string]$Kind = "BUS_CCTV",
  [switch]$Loop,
  [double]$IntervalSec = 2.5
)
$ErrorActionPreference = "Stop"
if (-not $Token) { throw "Set URBANSENSE_TOKEN or pass -Token. This script runs on the PC next to the DVR — UrbanSense ships no camera box." }
if ($SnapshotUrl -match '^rtsp://') { throw "This script pulls one JPEG. It does not decode RTSP. Use a DVR snapshot URL, or python ai/urbansense_ai/run_camera.py --source rtsp://..." }
if ($IntervalSec -lt 0.5) { $IntervalSec = 0.5 }

$tmp = Join-Path $env:TEMP ("urbansense-" + $Code + ".jpg")
$headers = @{ Authorization = "Bearer $Token" }
$ingestUri = $Api.TrimEnd("/") + "/ingest/cctv/still"

function Send-Snapshot {
  Invoke-WebRequest -Uri $SnapshotUrl -OutFile $tmp -TimeoutSec 12
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
  $res = Invoke-RestMethod -Method Post -Uri $ingestUri -Headers $headers -Form $form
  Write-Host ("Ingested " + $res.event.public_code + " · " + $res.event.event_type)
}

if ($Loop) {
  Write-Host "Depot JPEG loop every $IntervalSec s. Ctrl+C to stop. Not Azure GPU. Not RTSP decode."
  while ($true) {
    try {
      Send-Snapshot
    } catch {
      Write-Warning $_
    }
    Start-Sleep -Seconds $IntervalSec
  }
} else {
  Write-Host "Pulling one JPEG (not RTSP video) from the DVR..."
  Send-Snapshot
}
