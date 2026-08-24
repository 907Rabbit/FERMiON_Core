[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $SourceManifest,
    [Parameter(Mandatory = $true)] [string] $SourceManifestRawSha256,
    [string] $Root = "G:\MyAIproject",
    [string] $Output = "G:\MyAIproject\artifacts\ai_g2s_p1_1_full"
)

$ErrorActionPreference = "Stop"
$expectedP10 = "8F458D3CA9822897A7FBB7FF92314E312B37E9DF11E113E102D58DF71EACB8AD"
$expectedP11 = "BBDAB6671494069BBA94D9E2D0382D9A91896C634BEB83A315E7936FC961B03C"
$expectedSources = @(
    "fermion/ai_g1/ai_g2s_r1.py",
    "fermion/ai_g1/ai_g2s.py",
    "fermion/ai_g1/spectral.py",
    "fermion/ai_g1/diagnostics.py",
    "fermion/hr/reference_193.py"
)

function Get-RawSha256([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }
if ((Get-RawSha256 $SourceManifest) -ne $SourceManifestRawSha256.ToUpperInvariant()) { throw "raw source-manifest SHA-256 mismatch" }
if ((Get-RawSha256 (Join-Path $Root "configs/ai_g2s_p1_0.json")) -ne $expectedP10) { throw "P1.0 raw SHA-256 mismatch" }
if ((Get-RawSha256 (Join-Path $Root "configs/ai_g2s_p1_1.json")) -ne $expectedP11) { throw "P1.1 raw SHA-256 mismatch" }

$manifest = Get-Content -Raw -LiteralPath $SourceManifest | ConvertFrom-Json
$observed = @($manifest.entries | ForEach-Object { $_.path })
if (@(Compare-Object $expectedSources $observed).Count -ne 0 -or $observed.Count -ne $expectedSources.Count) { throw "source-set addition, omission, or duplicate" }
foreach ($entry in $manifest.entries) {
    if ((Get-RawSha256 (Join-Path $Root $entry.path)) -ne $entry.sha256.ToUpperInvariant()) { throw "source raw SHA-256 mismatch: $($entry.path)" }
}

$env:PYTHONHASHSEED = "0"
$env:CUBLAS_WORKSPACE_CONFIG = ":4096:8"
$python = Join-Path $Root ".venv/Scripts/python.exe"
$code = "from pathlib import Path; from fermion.ai_g1.ai_g2s_r1 import FullPairedRunner; r=Path(r'$Root'); FullPairedRunner(r,Path(r'$Output'),source_manifest_path=Path(r'$SourceManifest'),source_manifest_raw_sha256='$SourceManifestRawSha256').run(allow_final_test=True)"
& $python -c $code
if ($LASTEXITCODE -ne 0) { throw "AI-G2S-P1.1 run failed" }
