$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location "$root/backend"
try { & .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log }
finally { Pop-Location }
