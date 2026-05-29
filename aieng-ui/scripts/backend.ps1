param(
  [switch]$Force  # kill any existing listener on the port before starting
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PlatformRoot = Resolve-Path (Join-Path $ScriptDir "..")
$WorkspaceRoot = Split-Path -Parent $PlatformRoot
$BackendRoot = Join-Path $PlatformRoot "backend"
$Port = 8000

# Guard against accidental double-start: two uvicorn processes on the same port
# leave the socket in a half-broken state where it accepts TCP connections but
# never answers HTTP. Detect an existing listener and refuse (or kill with -Force).
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
  $pids = $existing | Select-Object -ExpandProperty OwningProcess -Unique
  if ($Force) {
    foreach ($processId in $pids) {
      Write-Host "Stopping existing listener on port $Port (PID $processId)…"
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
  } else {
    Write-Host "ERROR: port $Port is already in use by PID(s): $($pids -join ', ')." -ForegroundColor Red
    Write-Host "A backend may already be running. Re-run with -Force to replace it, or stop it first:" -ForegroundColor Yellow
    Write-Host "  Stop-Process -Id $($pids -join ',') -Force"
    exit 1
  }
}

# Candidate Python interpreters. The default runtime is build123d/OCP, so prefer
# a normal Python environment that can import build123d. FreeCAD remains an
# optional adapter and is no longer the preferred backend interpreter.
$FreeCADHome = Join-Path $WorkspaceRoot "FreeCAD_1.1.1-Windows-x86_64-py311"
$FreeCADPython = Join-Path $FreeCADHome "bin\python.exe"
$CondaPython = "C:\Users\RL_Carla\anaconda3\envs\aieng311\python.exe"
$EnvPython = $env:AIENG_PYTHON
$PathPythonCmd = Get-Command python -ErrorAction SilentlyContinue
$PathPython = if ($PathPythonCmd) { $PathPythonCmd.Source } else { $null }

function Test-HasBuild123d($py) {
  if (-not (Test-Path $py)) { return $false }
  & $py -c "import build123d" 2>$null
  return $LASTEXITCODE -eq 0
}

$PythonExe = $null
$ExtraEnv = @{}

$Candidates = @(
  @{ Label = "AIENG_PYTHON"; Path = $EnvPython },
  @{ Label = "conda env aieng311"; Path = $CondaPython },
  @{ Label = "PATH python"; Path = $PathPython },
  @{ Label = "FreeCAD embedded Python"; Path = $FreeCADPython }
)

foreach ($candidate in $Candidates) {
  $path = $candidate.Path
  if ($path -and (Test-HasBuild123d $path)) {
    $PythonExe = $path
    Write-Host "Selected $($candidate.Label) (build123d available): $PythonExe"
    break
  }
}

if (-not $PythonExe) {
  throw "No Python with build123d found. Set AIENG_PYTHON or install build123d into the aieng311 environment."
}

if (Test-Path $FreeCADHome) {
  $ExtraEnv["FREECAD_MCP_FREECAD_PATH"] = $FreeCADHome
}

foreach ($kv in $ExtraEnv.GetEnumerator()) {
  Set-Item -Path "env:$($kv.Key)" -Value $kv.Value
}

Set-Location $BackendRoot
& $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
