# Start the personal-ai-agent (Windows PowerShell)
# Usage: .\scripts\start.ps1

param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

# Navigate to the project root (one level up from scripts/)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Check for .env
if (-not (Test-Path ".env")) {
    Write-Warning ".env file not found. Copying from .env.example ..."
    Copy-Item ".env.example" ".env"
    Write-Host "Edit .env and set your GROQ_API_KEY before rerunning." -ForegroundColor Yellow
    exit 1
}

# Check if virtual environment exists
if (-not (Test-Path ".venv\Scripts\activate.ps1")) {
    Write-Host "Creating virtual environment ..." -ForegroundColor Cyan
    python -m venv .venv
}

# Activate venv
. ".venv\Scripts\activate.ps1"

# Install dependencies
Write-Host "Installing dependencies ..." -ForegroundColor Cyan
pip install -r requirements.txt --quiet

# Build uvicorn command
$UvicornArgs = @(
    "app.main:app",
    "--host", $Host,
    "--port", $Port
)
if ($Reload) {
    $UvicornArgs += "--reload"
}

Write-Host ""
Write-Host "=======================================" -ForegroundColor Green
Write-Host "  personal-ai-agent starting up"        -ForegroundColor Green
Write-Host "  http://$Host`:$Port/docs"              -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host ""

uvicorn @UvicornArgs
