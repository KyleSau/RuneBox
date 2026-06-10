$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "triposr_generate.py"
$Out = Join-Path $Root "outputs\smoke_test"

if (-not (Test-Path $Py)) { Write-Error "Run .\install.ps1 first." }

Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Out | Out-Null

Write-Host "== TripoSR backend smoke test ==" -ForegroundColor Cyan
& $Py $Script --prompt "low-poly bronze dagger, game asset" --output $Out --seed 42
if ($LASTEXITCODE -ne 0) { Write-Error "triposr_generate.py failed" }

$Meshes = Get-ChildItem -Path $Out -Recurse -Include *.obj,*.glb -File
if (-not $Meshes) { Write-Error "No mesh under $Out" }

$Mesh = $Meshes | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "PASS: $($Mesh.FullName)" -ForegroundColor Green
