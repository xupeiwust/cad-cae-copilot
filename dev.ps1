$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DevPy = Join-Path (Join-Path $ScriptDir "scripts") "dev.py"

$PythonCandidates = @(
    $env:AIENG_PYTHON,
    "python",
    "py"
) | Where-Object { $_ -and $_.Trim().Length -gt 0 }

$Python = $null

foreach ($Candidate in $PythonCandidates) {
    try {
        if ($Candidate -eq "py") {
            & py -3 --version *> $null
            $Python = "py -3"
        } else {
            & $Candidate --version *> $null
            $Python = $Candidate
        }
        break
    } catch {
        continue
    }
}

if (-not $Python) {
    Write-Error "[dev.ps1] Could not find Python. Try activating your conda environment first."
    exit 1
}

Write-Host "[dev.ps1] Using Python: $Python"
Write-Host "[dev.ps1] Starting backend + frontend..."

if ($Python -eq "py -3") {
    & py -3 $DevPy
} else {
    & $Python $DevPy
}