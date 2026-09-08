$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$trackedSecretPatterns = 'AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{20,}|(OPENWEATHER_API_KEY|WEATHERAPI_KEY|GEMINI_API_KEY)\s*=\s*\S+'
$hits = & rg -n --hidden --glob '!.git/**' --glob '!docs/MASTER_SPEC.md' --glob '!backend/.venv/**' --glob '!android/**/build/**' --glob '!.tools/**' $trackedSecretPatterns .
if ($LASTEXITCODE -eq 0) {
    Write-Error "Possible committed secret found:`n$hits"
}
if ($LASTEXITCODE -gt 1) { throw 'Repository scan failed.' }

if (-not (Select-String -Path .gitignore -Pattern '^\.env$' -Quiet)) { throw '.env is not ignored.' }
Write-Host 'Repository secret and ignore audit passed.'
