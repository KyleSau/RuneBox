# Install Hunyuan3D backend venv + vendor repo for RS model pipeline.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== Hunyuan3D backend install ==" -ForegroundColor Cyan

$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PyLauncher) {
    $PyBase = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
} else {
    $PyBase = $null
}
if (-not $PyBase) {
    throw "Python 3.10 required (py -3.10). Hunyuan3D is tested on 3.10."
}

if (Test-Path ".venv") {
    Write-Host "Removing existing venv (recreate with Python 3.10) ..."
    Remove-Item -Recurse -Force .venv
}

Write-Host "Creating venv with $PyBase ..."
& $PyBase -m venv .venv

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"

Write-Host "Upgrading pip ..."
& $Py -m pip install --upgrade pip setuptools wheel

Write-Host "Installing PyTorch (CUDA 12.4 wheels) ..."
& $Pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

Write-Host "Installing wrapper requirements ..."
& $Pip install -r requirements.txt
& $Pip install sentencepiece tiktoken

$Vendor = Join-Path $Root "_vendor\Hunyuan3D-2"
if (-not (Test-Path $Vendor)) {
    Write-Host "Cloning Tencent Hunyuan3D-2 (shape-only; no texture compile) ..."
    git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git $Vendor
} else {
    Write-Host "Vendor repo already present: $Vendor"
}

Write-Host "Installing hy3dgen package ..."
& $Pip install -e $Vendor

$Script = Join-Path $Root "hunyuan_generate.py"
Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host ""
Write-Host "Set RS_HUNYUAN3D_COMMAND for the RS pipeline:" -ForegroundColor Yellow
Write-Host ('$env:RS_HUNYUAN3D_COMMAND="{0} {1}"' -f $Py, $Script)
Write-Host ""
Write-Host "First run downloads ~8-15 GB of model weights from Hugging Face." -ForegroundColor Yellow
Write-Host "Shape-only defaults target 8-12 GB VRAM (mini turbo + FlashVDM)." -ForegroundColor Yellow
Write-Host "Run backend smoke test: .\test.ps1" -ForegroundColor Yellow
