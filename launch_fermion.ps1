param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$model = 'F:\models\lmstudio-community\Qwen3-4B-Thinking-2507-GGUF\Qwen3-4B-Thinking-2507-Q8_0.gguf'

if (-not (Test-Path -LiteralPath $python)) {
    throw "FERMiON virtual environment was not found: $python"
}
if (-not (Test-Path -LiteralPath $model)) {
    throw "Configured GGUF model was not found: $model"
}

Set-Location -LiteralPath $projectRoot
Write-Host 'Starting FERMiON with Qwen3-4B-Thinking-2507 (local GGUF)...' -ForegroundColor Cyan
& $python -m fermion llama start
if ($LASTEXITCODE -ne 0) { throw 'The local llama.cpp server failed to start. Check .fermion\llama-server.stderr.log.' }
& $python -m fermion --model $model chat
