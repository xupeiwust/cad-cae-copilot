#!/usr/bin/env python3
"""Cross-platform dev launcher for the aieng workbench.

Starts the active backend (FastAPI + uvicorn) and frontend (Vite) concurrently.
Works on Windows, macOS, Linux, and WSL.

Usage:
    python scripts/dev.py                    # start both
    BACKEND_PORT=8080 python scripts/dev.py  # custom backend port
    FRONTEND_PORT=3000 python scripts/dev.py # custom frontend port

Platform wrappers:
    Windows PowerShell: \\.dev.ps1
    macOS/Linux/WSL:    ./scripts/dev.sh   or   make dev
"""
from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "5173"))
BACKEND_HOST = "127.0.0.1"

# ---------------------------------------------------------------------------
# Locate repository root
# ---------------------------------------------------------------------------


def find_repo_root() -> Path:
    """Resolve repo root from the script location."""
    script_path = Path(__file__).resolve()
    # scripts/dev.py -> repo root is one level up
    return script_path.parents[1]


REPO_ROOT = find_repo_root()
BACKEND_DIR = REPO_ROOT / "aieng-ui" / "backend"
FRONTEND_DIR = REPO_ROOT / "aieng-ui" / "frontend"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[dev] {msg}", flush=True)


def error(msg: str) -> None:
    print(f"[dev] ERROR: {msg}", file=sys.stderr, flush=True)


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def find_python() -> str | None:
    """Find a suitable Python interpreter for the backend."""
    # 1. Explicit override
    env_py = os.environ.get("AIENG_PYTHON")
    if env_py and shutil.which(env_py):
        return env_py

    # 2. Try 'python' (common on Windows and venvs)
    if has_command("python"):
        return "python"

    # 3. Try 'python3' (common on macOS/Linux)
    if has_command("python3"):
        return "python3"

    # 4. Try the known conda env path on Windows
    if platform.system() == "Windows":
        conda_py = Path.home() / "anaconda3" / "envs" / "aieng311" / "python.exe"
        if conda_py.exists():
            return str(conda_py)

    # 5. Try common conda path on macOS/Linux
    for prefix in (Path.home() / "anaconda3", Path.home() / "miniconda3", Path.home() / ".conda"):
        conda_py = prefix / "envs" / "aieng311" / "bin" / "python"
        if conda_py.exists():
            return str(conda_py)

    return None


def check_backend_env(python: str) -> bool:
    """Verify that the chosen Python can import build123d (core backend dep)."""
    result = subprocess.run(
        [python, "-c", "import build123d"],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def preflight() -> str:
    """Run all startup checks and return the Python executable path."""
    errors: list[str] = []

    if not BACKEND_DIR.is_dir():
        errors.append(f"Backend directory not found: {BACKEND_DIR}")
    if not FRONTEND_DIR.is_dir():
        errors.append(f"Frontend directory not found: {FRONTEND_DIR}")

    backend_entry = BACKEND_DIR / "app" / "main.py"
    if not backend_entry.is_file():
        errors.append(f"Backend entrypoint not found: {backend_entry}")

    python = find_python()
    if not python:
        errors.append(
            "No suitable Python interpreter found. "
            "Install Python 3.11+, create the 'aieng311' conda env, "
            "or set AIENG_PYTHON to the correct interpreter."
        )
    elif not check_backend_env(python):
        errors.append(
            f"Python ({python}) cannot import build123d. "
            "Install the backend dependencies first:\n"
            f"  cd {BACKEND_DIR} && pip install -e ."
        )

    if not has_command("npm"):
        errors.append("npm not found in PATH. Install Node.js (v20+ recommended).")

    if errors:
        error("Preflight failed — cannot start:\n" + "\n".join(f"  - {e}" for e in errors))
        sys.exit(1)

    return python  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

_procs: list[subprocess.Popen[str]] = []


def cleanup(signum: int | None = None, frame=None) -> None:
    """Terminate all tracked child processes."""
    log("Shutting down services...")
    for proc in _procs:
        if proc.poll() is None:
            try:
                if platform.system() == "Windows":
                    proc.terminate()
                else:
                    # Send SIGTERM to the process group on Unix
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    # Give them a moment to exit gracefully
    deadline = time.time() + 5.0
    for proc in _procs:
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    log("Done.")
    sys.exit(0)


def start_backend(python: str) -> subprocess.Popen[str]:
    cmd = [
        python, "-m", "uvicorn",
        "app.main:app",
        "--host", BACKEND_HOST,
        "--port", str(BACKEND_PORT),
        "--reload",
    ]
    log(f"Starting backend: {' '.join(cmd)}")
    kwargs: dict[str, object] = {
        "cwd": BACKEND_DIR,
        "stdout": sys.stdout,
        "stderr": sys.stderr,
    }
    if platform.system() != "Windows":
        kwargs["preexec_fn"] = os.setsid  # new process group for clean group-kill
    proc = subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]
    return proc


def start_frontend() -> subprocess.Popen[str]:
    # Ensure node_modules exists
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.is_dir():
        log("Installing frontend dependencies (npm install)...")
        install_result = subprocess.run(
            ["npm", "install"],
            cwd=FRONTEND_DIR,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        if install_result.returncode != 0:
            error("npm install failed.")
            sys.exit(1)

    # Vite does not accept a --port flag via 'npm run dev' easily unless we pass
    # it through the CLI or VITE_* env vars. We use -- --port for npm scripts.
    cmd = ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT)]
    log(f"Starting frontend: {' '.join(cmd)}")
    kwargs: dict[str, object] = {
        "cwd": FRONTEND_DIR,
        "stdout": sys.stdout,
        "stderr": sys.stderr,
    }
    if platform.system() != "Windows":
        kwargs["preexec_fn"] = os.setsid
    proc = subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]
    return proc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    log(f"Repo root: {REPO_ROOT}")
    python = preflight()
    log(f"Using Python: {python}")

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, cleanup)

    backend_proc = start_backend(python)
    _procs.append(backend_proc)

    # Brief pause so backend logs start before frontend floods the terminal
    time.sleep(0.5)

    frontend_proc = start_frontend()
    _procs.append(frontend_proc)

    print()
    log("=" * 60)
    log("All services starting...")
    log("")
    log(f"  Frontend:     http://localhost:{FRONTEND_PORT}")
    log(f"  Backend:      http://{BACKEND_HOST}:{BACKEND_PORT}")
    log(f"  API Docs:     http://{BACKEND_HOST}:{BACKEND_PORT}/docs")
    log("")
    log("Press Ctrl+C to stop.")
    log("=" * 60)
    print()

    # Wait for either process to exit
    while True:
        backend_code = backend_proc.poll()
        frontend_code = frontend_proc.poll()

        if backend_code is not None and backend_code != 0:
            error(f"Backend exited with code {backend_code}.")
            cleanup()
            sys.exit(backend_code)

        if frontend_code is not None and frontend_code != 0:
            error(f"Frontend exited with code {frontend_code}.")
            cleanup()
            sys.exit(frontend_code)

        if backend_code is not None and frontend_code is not None:
            # Both exited cleanly
            break

        time.sleep(0.5)

    log("Both services have exited.")


if __name__ == "__main__":
    main()
