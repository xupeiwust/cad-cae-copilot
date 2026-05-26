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

# Two candidate Python interpreters. We prefer whichever can actually import
# build123d, because the backend's `Build123dBackend.can_generate()` gates
# text-to-CAD on that import — picking a Python without it makes the whole
# CAD pipeline 503 even though the host technically has FreeCAD installed.
$FreeCADHome = Join-Path $WorkspaceRoot "FreeCAD_1.1.1-Windows-x86_64-py311"
$FreeCADPython = Join-Path $FreeCADHome "bin\python.exe"
$CondaPython = "C:\Users\RL_Carla\anaconda3\envs\aieng311\python.exe"

function Test-HasBuild123d($py) {
  if (-not (Test-Path $py)) { return $false }
  & $py -c "import build123d" 2>$null
  return $LASTEXITCODE -eq 0
}

$PythonExe = $null
$ExtraEnv = @{}

# Preference order: a Python that can import build123d wins. Among interpreters
# that have build123d, prefer FreeCAD because it also unlocks the FreeCAD MCP
# integration path.
if (Test-HasBuild123d $FreeCADPython) {
  $PythonExe = $FreeCADPython
  $ExtraEnv["FREECAD_MCP_FREECAD_PATH"] = $FreeCADHome
  Write-Host "Selected FreeCAD embedded Python (build123d available): $PythonExe"
} elseif (Test-HasBuild123d $CondaPython) {
  $PythonExe = $CondaPython
  Write-Host "Selected conda env aieng311 (build123d available): $PythonExe"
} elseif (Test-Path $FreeCADPython) {
  # FreeCAD exists but lacks build123d — still usable for non-CAD endpoints.
  $PythonExe = $FreeCADPython
  $ExtraEnv["FREECAD_MCP_FREECAD_PATH"] = $FreeCADHome
  Write-Host "WARNING: FreeCAD Python does NOT have build123d — CAD generation will return 503."
  Write-Host "  To fix: install build123d into the conda env (aieng311) and either remove FreeCAD"
  Write-Host "  from this path or install build123d into FreeCAD's Python."
  Write-Host "  Falling back to: $PythonExe"
} elseif (Test-Path $CondaPython) {
  $PythonExe = $CondaPython
  Write-Host "WARNING: conda env aieng311 does NOT have build123d — CAD generation will return 503."
  Write-Host "  To fix: pip install build123d into aieng311."
  Write-Host "  Falling back to: $PythonExe"
} else {
  throw "No suitable Python found. Install FreeCAD at $FreeCADHome or create conda env aieng311 with build123d."
}

foreach ($kv in $ExtraEnv.GetEnumerator()) {
  Set-Item -Path "env:$($kv.Key)" -Value $kv.Value
}

Set-Location $BackendRoot
& $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
