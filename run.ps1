param(
  [int]$Port = 5000,
  [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Virtual environment not found. Creating .venv..." -ForegroundColor Yellow
  python -m venv .venv
}

Write-Host "Installing requirements into .venv..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not $SkipFrontendBuild -and (Test-Path "frontend\package.json")) {
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if ($npm) {
    Push-Location "frontend"
    try {
      if (-not (Test-Path "node_modules")) {
        Write-Host "Installing React frontend dependencies..." -ForegroundColor Cyan
        & $npm.Source install
      }

      Write-Host "Building React frontend..." -ForegroundColor Cyan
      & $npm.Source run build
    }
    finally {
      Pop-Location
    }
  }
  else {
    Write-Host "npm was not found. Serving Flask fallback UI." -ForegroundColor Yellow
  }
}

Write-Host "Starting server on http://127.0.0.1:$Port" -ForegroundColor Green
$env:FLASK_RUN_PORT = "$Port"
.\.venv\Scripts\python.exe app.py

