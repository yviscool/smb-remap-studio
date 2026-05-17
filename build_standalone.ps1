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

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "The virtual environment was not found. Run setup_remap_tool.ps1 first."
    exit 1
}

$null = Invoke-VenvPython -Args @("-m", "pip", "install", "-r", "requirements-build.txt")
$optionalExitCode = Invoke-VenvPython -Args @("-m", "pip", "install", "--only-binary=:all:", "-r", "requirements-optional.txt") -AllowFailure

if ($optionalExitCode -ne 0) {
    Write-Warning "Optional dependency pygame could not be installed. This build will not include gamepad auto-detect."
}

foreach ($path in @("build", "dist")) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

$null = Invoke-VenvPython -Args @("-m", "PyInstaller", "--noconfirm", "--clean", "smb_remap_tool.spec")

$builtBinary = Join-Path $scriptDir "dist\SMBRemapStudio.exe"
$targetBinary = Join-Path $scriptDir "SMBRemapStudio.exe"
Copy-Item -LiteralPath $builtBinary -Destination $targetBinary -Force

Write-Host "Build complete: $targetBinary"
