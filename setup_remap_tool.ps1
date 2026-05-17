$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

function Invoke-VenvPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args,
        [switch]$AllowFailure
    )

    & ".\.venv\Scripts\python.exe" @Args
    if ($LASTEXITCODE -ne 0 -and -not $AllowFailure) {
        throw "Command failed: python $($Args -join ' ')"
    }
    return $LASTEXITCODE
}

if (-not (Test-Path ".venv")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    else {
        throw "Python 3 was not found. Install Python 3 first."
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }
}

$null = Invoke-VenvPython -Args @("-m", "pip", "install", "--upgrade", "pip")
$null = Invoke-VenvPython -Args @("-m", "pip", "install", "-r", "requirements.txt")
$optionalExitCode = Invoke-VenvPython -Args @("-m", "pip", "install", "--only-binary=:all:", "-r", "requirements-optional.txt") -AllowFailure

if ($optionalExitCode -ne 0) {
    Write-Warning "Optional dependency pygame could not be installed. Gamepad auto-detect will be unavailable."
    Write-Warning "Reading, editing, and saving buttonmap.cfg still works."
}

Write-Host "Dependencies installed."
Write-Host "Run with: powershell -ExecutionPolicy Bypass -File .\run_remap_tool.ps1"
