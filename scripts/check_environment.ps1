$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Write-Host "WeatherGPT environment at $root"
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (Test-Path $python) { & $python --version } else { Write-Warning 'Backend virtual environment is missing. Run scripts\setup_backend.ps1.' }
$java = 'C:\Program Files\Android\Android Studio\jbr\bin\java.exe'
if (Test-Path $java) { & $java -version } else { Write-Warning 'Android Studio JBR was not found at the expected path.' }
$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
if (Test-Path $sdk) { Write-Host "Android SDK: $sdk" } else { Write-Warning 'Android SDK was not found.' }
$gradleZip = Join-Path $root '.tools\gradle-9.3.1-bin.zip'
if (Test-Path $gradleZip) { Write-Host "Local Gradle distribution: $gradleZip" } else { Write-Warning 'Local Gradle distribution is missing.' }
