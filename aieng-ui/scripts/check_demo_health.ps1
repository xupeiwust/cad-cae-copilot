#requires -Version 5.1
<#
.SYNOPSIS
  Runs the AIENG demo health gate locally.

.DESCRIPTION
  Executes the narrow smoke-check test suite, optionally the full backend
  tests, and optionally the frontend build. Returns non-zero exit code on
  failure so it can be used as a local CI gate.

.EXAMPLE
  .\scripts\check_demo_health.ps1
  .\scripts\check_demo_health.ps1 -Full
  .\scripts\check_demo_health.ps1 -Frontend
#>
[CmdletBinding()]
param(
  [switch]$Full,
  [switch]$Frontend
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PlatformRoot = Resolve-Path (Join-Path $ScriptDir "..")
$BackendRoot = Join-Path $PlatformRoot "backend"
$FrontendRoot = Join-Path $PlatformRoot "frontend"

$failed = $false

function Run-Step($Label, $WorkDir, $Command) {
  Write-Host "`n==> $Label" -ForegroundColor Cyan
  try {
    Push-Location $WorkDir
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) { throw "Exit code $LASTEXITCODE" }
    Write-Host "OK: $Label" -ForegroundColor Green
  } catch {
    Write-Host "FAIL: $Label`n$_" -ForegroundColor Red
    $script:failed = $true
  } finally {
    Pop-Location
  }
}

# Mandatory: smoke-check tests
Run-Step "Backend smoke-check tests" $BackendRoot "python -m pytest -q -k 'smoke_check'"

if ($Full) {
  Run-Step "Full backend tests" $BackendRoot "python -m pytest -q"
}

if ($Frontend -or $Full) {
  Run-Step "Frontend build" $FrontendRoot "npm run build"
}

if ($failed) {
  Write-Host "`nDemo health gate FAILED." -ForegroundColor Red
  exit 1
} else {
  Write-Host "`nDemo health gate PASSED." -ForegroundColor Green
  exit 0
}
