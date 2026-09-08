param([string]$Python='py')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    & $Python -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Pass -Python with its executable path.' }
    & backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
} finally { Pop-Location }
