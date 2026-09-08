$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:GRADLE_USER_HOME=Join-Path $root '.tools/gradle'
if (-not $env:JAVA_HOME) { $env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr' }
Push-Location "$root/android"
try { & ./gradlew.bat assembleDebug testDebugUnitTest lintDebug --console=plain; exit $LASTEXITCODE }
finally { Pop-Location }
