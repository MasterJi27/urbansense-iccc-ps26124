<#
Build the Flutter app (mobile/) into a release APK on this Windows box.

  .\scripts\build-apk.ps1                          # arm64 APK -> mobile\build\apk\SadakSaarthi-<version>-arm64.apk
  .\scripts\build-apk.ps1 -LowPriority             # same, but easy on the CPU (use while training runs)
  .\scripts\build-apk.ps1 -ApiBase https://host    # point the app at another server (default: the Azure URL in the code)

Why a copy of mobile/ is built instead of mobile/ itself:
  * Flutter on Windows needs symlinks for plugins while mobile/windows exists. That needs Windows Developer
    Mode, which is a system setting. The copy leaves windows/ out, so no Developer Mode is needed.
    If you turn Developer Mode on, `flutter build apk` inside mobile/ works too.
  * TEMP is pointed at a short folder on D:. JDK 21 builds its selector pipe from an AF_UNIX socket in TEMP and
    that fails in C:\Users\...\AppData\Local\Temp here ("Unable to establish loopback connection"), so every
    Gradle run died.
The APK is signed with the debug key (see mobile/android/app/build.gradle.kts): fine for installing on phones,
not for the Play Store. A Play Store release needs your own keystore.
#>
param(
    [string]$Flutter = 'D:\tools\flutter',
    [string]$Work = 'D:\tools\apk_build',
    [string]$Tmp = 'D:\tools\tmp',
    [string]$ApiBase = '',
    [string]$Platform = 'android-arm64',
    [switch]$LowPriority
)
# Continue, not Stop: Windows PowerShell 5.1 turns a native command's stderr (flutter prints warnings there) into a
# terminating error under Stop. Native calls are checked through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$repo =Split-Path -Parent $PSScriptRoot
$src = Join-Path $repo 'mobile'
if (-not (Test-Path "$Flutter\bin\flutter.bat")) { throw "Flutter SDK not found at $Flutter (git clone -b stable https://github.com/flutter/flutter.git $Flutter)" }

if ($LowPriority) { (Get-Process -Id $PID).PriorityClass = 'BelowNormal' }
New-Item -ItemType Directory -Force $Tmp, $Work -ErrorAction Stop | Out-Null
$env:TEMP = $Tmp
$env:TMP = $Tmp
$env:Path = "$Flutter\bin;$env:Path"
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk" }

robocopy $src $Work /MIR /XD windows build .dart_tool .gradle .idea /XF '._*' local.properties '*.iml' .flutter-plugins-dependencies /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }

$props = Join-Path $Work 'android\gradle.properties'
$extra = @('kotlin.incremental=false')   # pub cache (C:) and project (D:) on different drives break Kotlin incremental builds
if ($LowPriority) { $extra += 'org.gradle.workers.max=2', 'org.gradle.parallel=false' }
$have = Get-Content $props
foreach ($line in $extra) { if ($have -notcontains $line) { Add-Content $props $line } }

Push-Location $Work
try {
    flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub get failed' }
    $args = @('build', 'apk', '--release', '--target-platform', $Platform)
    if ($ApiBase) { $args += "--dart-define=API_BASE=$ApiBase" }
    flutter @args
    if ($LASTEXITCODE -ne 0) { throw 'flutter build apk failed' }
} finally {
    Pop-Location
}

$built = Join-Path $Work 'build\app\outputs\flutter-apk\app-release.apk'
if (-not (Test-Path $built)) { throw "build reported success but $built is missing" }
$version = ((Get-Content (Join-Path $src 'pubspec.yaml')) | Where-Object { $_ -match '^version:\s*([^+\s]+)' } | ForEach-Object { $Matches[1] } | Select-Object -First 1)
$abi = $Platform -replace '^android-', ''
$outDir = Join-Path $src 'build\apk'
New-Item -ItemType Directory -Force $outDir -ErrorAction Stop | Out-Null
$out = Join-Path $outDir "SadakSaarthi-$version-$abi.apk"
Copy-Item $built $out -Force -ErrorAction Stop
"APK: $out ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)"
"SHA256: $((Get-FileHash $out -Algorithm SHA256).Hash)"
