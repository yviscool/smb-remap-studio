$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "The virtual environment was not found. Run setup_remap_tool.ps1 first."
    exit 1
}

& ".\.venv\Scripts\python.exe" "smb_remap_tool.py" @args
exit $LASTEXITCODE
