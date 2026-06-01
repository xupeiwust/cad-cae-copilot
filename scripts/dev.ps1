# Cross-platform dev launcher wrapper for Windows PowerShell.
# Usage: .\scripts\dev.ps1   (from repo root)
#
# This simply delegates to scripts/dev.py, trying common Python commands.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$DevPy = Join-Path $ScriptDir "dev.py"

function Find-Python {
    $envPy = $env:AIENG_PYTHON
    if ($envPy -and (Test-Path $envPy)) { return $envPy }
    $condaPy = "$env:USERPROFILE\anaconda3\envs\aieng311\python.exe"
    if (Test-Path $condaPy) { return $condaPy }
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) { return "py -3" }
    $pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCmd) { return $pythonCmd.Source }
    $python3Cmd = Get-Command "python3" -ErrorAction SilentlyContinue
    if ($python3Cmd) { return $python3Cmd.Source }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Error "No Python found. Install Python 3.11+, set AIENG_PYTHON, or use the aieng311 conda env."
    exit 1
}

Write-Host "[scripts/dev.ps1] Using Python: $python"
Write-Host "[scripts/dev.ps1] Starting backend + frontend..."

Set-Location $RepoRoot
& $python $DevPy
