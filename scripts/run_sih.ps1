# WeatherGPT SIH one-click local run (Windows)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$adb = Join-Path $sdk 'platform-tools\adb.exe'
$emulator = Join-Path $sdk 'emulator\emulator.exe'
$javaHome = 'C:\Program Files\Android\Android Studio\jbr'
$avd = 'Pixel_10a'

Write-Host '== WeatherGPT SIH launcher =='

# Backend
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2
    Write-Host "Backend already running: $($health.status)"
} catch {
    Write-Host 'Starting backend on :8000 ...'
    Start-Process -FilePath (Join-Path $root 'backend\.venv\Scripts\python.exe') `
        -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000','--no-access-log') `
        -WorkingDirectory (Join-Path $root 'backend') `
        -WindowStyle Minimized
    Start-Sleep -Seconds 3
    $health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 5
    Write-Host "Backend: $($health.status)"
}

# Emulator
$devices = & $adb devices | Select-String 'emulator-|device$'
if (-not $devices) {
    Write-Host "Starting emulator $avd ..."
    Start-Process -FilePath $emulator -ArgumentList @('-avd', $avd, '-netdelay', 'none', '-netspeed', 'full')
}
Write-Host 'Waiting for Android device...'
& $adb wait-for-device
$deadline = (Get-Date).AddMinutes(3)
do {
    $boot = (& $adb shell getprop sys.boot_completed 2>$null).Trim()
    if ($boot -eq '1') { break }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)
if ($boot -ne '1') { throw 'Emulator did not finish booting in time.' }

# Choose the backend address the app will use.
#
# 10.0.2.2 is the emulator's alias for the host, but reaching it means an inbound connection to
# python.exe on the host, which Windows Firewall blocks by default. `adb reverse` tunnels the
# device's own 127.0.0.1:8000 to the host over the adb channel instead, which needs no admin
# rights and no firewall change. Probe the direct route first and fall back to the tunnel.
& $adb reverse tcp:8000 tcp:8000 | Out-Null
$probe = & $adb shell "echo -e 'GET /health HTTP/1.0\r\n\r' | timeout 5 nc 10.0.2.2 8000 2>/dev/null | head -1"
if ("$probe" -match '200') {
    $apiUrl = 'http://10.0.2.2:8000/'
    Write-Host "Backend reachable directly at $apiUrl"
} else {
    $apiUrl = 'http://127.0.0.1:8000/'
    Write-Host 'Direct 10.0.2.2:8000 is blocked (most likely Windows Firewall).'
    Write-Host "Using the adb reverse tunnel instead: $apiUrl"
    Write-Host 'To use 10.0.2.2 directly, run this once in an ADMIN PowerShell:'
    Write-Host "  New-NetFirewallRule -DisplayName 'WeatherGPT dev backend' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Program '$root\backend\.venv\Scripts\python.exe' -Profile Private"
}

# Build + install
$env:JAVA_HOME = $javaHome
Push-Location (Join-Path $root 'android')
try {
    Write-Host 'Building and installing debug APK...'
    & .\gradlew.bat installDebug "-Pweathergpt.apiUrl=$apiUrl"
    if ($LASTEXITCODE -ne 0) { throw 'Gradle installDebug failed' }
} finally {
    Pop-Location
}

Write-Host 'Launching WeatherGPT...'
& $adb shell am start -n in.weathergpt/.MainActivity | Out-Host
Write-Host ''
Write-Host "Ready. The app is built against $apiUrl"
Write-Host 'Open Chat, choose a place (e.g. Delhi), ask: Will it rain tomorrow?'
