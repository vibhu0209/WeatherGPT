$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location "$root/backend"
try { & .venv/Scripts/python.exe -m pytest -q; exit $LASTEXITCODE }
finally { Pop-Location }
