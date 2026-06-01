#!/usr/bin/env bash
# Cross-platform dev launcher wrapper for macOS / Linux / WSL.
# Usage: ./scripts/dev.sh   (from repo root)
#
# This simply delegates to scripts/dev.py, trying python3 first, then python.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEV_PY="${SCRIPT_DIR}/dev.py"

find_python() {
    # 1. Explicit override
    if [ -n "${AIENG_PYTHON:-}" ] && command -v "$AIENG_PYTHON" >/dev/null 2>&1; then
        echo "$AIENG_PYTHON"
        return
    fi
    # 2. python3
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return
    fi
    # 3. python
    if command -v python >/dev/null 2>&1; then
        echo "python"
        return
    fi
    # 4. conda env
    for prefix in "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/.conda"; do
        if [ -x "$prefix/envs/aieng311/bin/python" ]; then
            echo "$prefix/envs/aieng311/bin/python"
            return
        fi
    done
    echo ""
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
    echo "[scripts/dev.sh] ERROR: No Python found. Install Python 3.11+, set AIENG_PYTHON, or use the aieng311 conda env." >&2
    exit 1
fi

echo "[scripts/dev.sh] Using Python: $PYTHON"
echo "[scripts/dev.sh] Starting backend + frontend..."

cd "$REPO_ROOT"
exec "$PYTHON" "$DEV_PY"
