$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== TripoSR backend install (lighter fallback) ==" -ForegroundColor Cyan

$PyBase = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
if (-not $PyBase) { throw "Python 3.10 required (py -3.10)." }

if (Test-Path ".venv") {
    Write-Host "Removing existing venv ..."
    Remove-Item -Recurse -Force .venv
}

& $PyBase -m venv .venv

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"

& $Py -m pip install --upgrade pip setuptools wheel
& $Pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
& $Pip install -r requirements.txt

$Vendor = Join-Path $Root "_vendor\TripoSR"
if (-not (Test-Path $Vendor)) {
    Write-Host "Cloning TripoSR ..."
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git $Vendor
}

Write-Host "Installing TripoSR dependencies (relaxed pins for Windows/py310) ..."
& $Pip install omegaconf einops trimesh rembg huggingface-hub xatlas moderngl "imageio[ffmpeg]"
& $Pip install "transformers>=4.35,<5"
Write-Host "Building torchmcubes (requires CUDA toolkit + MSVC) ..."
& $Pip install git+https://github.com/tatsy/torchmcubes.git
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "WARNING: torchmcubes build failed on this machine." -ForegroundColor Yellow
    Write-Host "TripoSR may not run on Windows until torchmcubes installs." -ForegroundColor Yellow
    Write-Host "Use Hunyuan3D backend instead, or run TripoSR on Linux/WSL." -ForegroundColor Yellow
}

$Script = Join-Path $Root "triposr_generate.py"
Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host ('$env:RS_TRIPOSR_COMMAND="{0} {1}"' -f $Py, $Script)
Write-Host "Smoke test: .\test.ps1"
