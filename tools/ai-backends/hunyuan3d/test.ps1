# Smoke test: generate a small mesh from a short text prompt.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "hunyuan_generate.py"
$Out = Join-Path $Root "outputs\smoke_test"

if (-not (Test-Path $Py)) {
    Write-Error "Backend venv missing. Run .\install.ps1 first."
}

if (-not (Test-Path $Script)) {
    Write-Error "hunyuan_generate.py not found."
}

Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Out | Out-Null

Write-Host "== Hunyuan3D backend smoke test ==" -ForegroundColor Cyan
Write-Host "Output: $Out"
Write-Host ""

$Prompt = "low-poly bronze dagger, simple game asset, white background"
& $Py $Script --prompt $Prompt --output $Out --seed 42 --steps 5 --octree-resolution 256
if ($LASTEXITCODE -ne 0) {
    Write-Error "hunyuan_generate.py failed (exit $LASTEXITCODE)"
}

$Meshes = Get-ChildItem -Path $Out -Recurse -Include *.obj,*.glb,*.ply,*.stl -File
if (-not $Meshes) {
    Write-Error "No mesh file found under $Out"
}

$Mesh = $Meshes | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ""
Write-Host "PASS: mesh generated" -ForegroundColor Green
Write-Host "Path: $($Mesh.FullName)"
Write-Host "Size: $([math]::Round($Mesh.Length / 1KB, 1)) KB"
