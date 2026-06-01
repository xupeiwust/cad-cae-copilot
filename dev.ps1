# Cross-platform dev launcher wrapper for Windows PowerShell.
# Usage: .\dev.ps1
#
# This simply delegates to scripts/dev.py, trying common Python commands.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DevPy = Join-Path $ScriptDir "scripts" "dev.py"

function Find-Python {
    # 1. AIENG_PYTHON override
    $envPy = $env:AIENG_PYTHON
    if ($envPy -and (Test-Path $envPy)) { return $envPy }
    # 2. conda env aieng311
    $condaPy = "$env:USERPROFILE\anaconda3\envs\aieng311\python.exe"
    if (Test-Path $condaPy) { return $condaPy }
    # 3. py -3 (Python Launcher for Windows)
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) { return "py -3" }
    # 4. python on PATH
    $pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCmd) { return $pythonCmd.Source }
    # 5. python3 on PATH (WSL / Git Bash)
    $python3Cmd = Get-Command "python3" -ErrorAction SilentlyContinue
    if ($python3Cmd) { return $python3Cmd.Source }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Error "No Python found. Install Python 3.11+, set AIENG_PYTHON, or use the aieng311 conda env."
    exit 1
}

Write-Host "[dev.ps1] Using Python: $python"
Write-Host "[dev.ps1] Starting backend + frontend..."

# Run dev.py from repo root so it can resolve paths correctly
Set-Location $ScriptDir
& $python $DevPy
