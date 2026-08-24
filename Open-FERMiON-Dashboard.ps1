$ErrorActionPreference = 'Stop'

$projectRoot = 'G:\MyAIproject'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$dashboardUrl = 'http://127.0.0.1:8765'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "FERMiON Python environment was not found: $python"
}

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $listener) {
    Start-Process -FilePath $python -ArgumentList '-m fermion dashboard' `
        -WorkingDirectory $projectRoot -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Start-Process $dashboardUrl
