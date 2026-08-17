# PowerShell startup wrapper for the verified Beta-v2 launcher.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $scriptDir ".venv\Scripts\python.exe"
$launcher = Join-Path $scriptDir "run.py"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error "Beta-v2 virtual environment is missing. Follow README.md first-time setup."
    exit 1
}

& $python $launcher
exit $LASTEXITCODE
