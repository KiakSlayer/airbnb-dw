# setup.ps1 — create .venv and install project dependencies
# Run from the project root: .\setup.ps1

$ErrorActionPreference = "Stop"

# Check Python version
$pythonVersion = python --version 2>&1
Write-Host "Found: $pythonVersion"
if (-not ($pythonVersion -match "Python 3\.(\d+)") -or [int]$Matches[1] -lt 8) {
    Write-Error "Python 3.8+ required."
    exit 1
}

# Create .venv if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..."
    python -m venv .venv
} else {
    Write-Host ".venv already exists, skipping creation."
}

# Activate and install
Write-Host "Activating .venv and installing requirements..."
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

# Verify imports
Write-Host "`nVerifying installs..."
python -c "import pandas, numpy, boto3, psycopg2, openpyxl, requests; print('All packages OK')"

# Install /start-session Claude Code skill
$skillSrc = ".\.claude\skills\start-session\SKILL.md"
$skillDst = "$env:USERPROFILE\.claude\skills\start-session"
if (Test-Path $skillSrc) {
    Write-Host "`nInstalling /start-session Claude Code skill..."
    New-Item -ItemType Directory -Force -Path $skillDst | Out-Null
    Copy-Item $skillSrc "$skillDst\SKILL.md" -Force
    Write-Host "  Skill installed. Use /start-session at the start of each Claude Code session."
}

Write-Host "`nSetup complete. Activate the environment with:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
