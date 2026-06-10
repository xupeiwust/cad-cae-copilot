#!/usr/bin/env bash
set -uo pipefail

backend_host="${AIENG_BACKEND_HOST:-0.0.0.0}"
backend_port="${AIENG_BACKEND_PORT:-8000}"
mcp_host="${AIENG_MCP_HOST:-0.0.0.0}"
mcp_port="${AIENG_MCP_PORT:-8765}"

export AIENG_PLATFORM_DATA="${AIENG_PLATFORM_DATA:-/data}"
export AIENG_ROOT="${AIENG_ROOT:-/opt/aieng/aieng}"
export AIENG_BACKEND_URL="${AIENG_BACKEND_URL:-http://127.0.0.1:${backend_port}}"
export AIENG_MCP_MANAGED_APPROVAL="${AIENG_MCP_MANAGED_APPROVAL:-1}"

echo "[aieng-docker] Ensuring data directory: ${AIENG_PLATFORM_DATA}"
mkdir -p "${AIENG_PLATFORM_DATA}" || {
    echo "[aieng-docker] FATAL: Cannot create ${AIENG_PLATFORM_DATA} — check volume permissions"
    exit 1
}

backend_pid=""
mcp_pid=""

shutdown() {
  echo "[aieng-docker] Shutting down..."
  if [[ -n "${mcp_pid}" ]] && kill -0 "${mcp_pid}" 2>/dev/null; then
    kill "${mcp_pid}" 2>/dev/null || true
    wait "${mcp_pid}" 2>/dev/null || true
  fi
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
    wait "${backend_pid}" 2>/dev/null || true
  fi
  echo "[aieng-docker] Shutdown complete"
}

trap shutdown SIGINT SIGTERM

# ----------------------------------------------------------------
# Start backend
# ----------------------------------------------------------------
echo "[aieng-docker] Starting backend on ${backend_host}:${backend_port}"
python -m uvicorn app.main:app --host "${backend_host}" --port "${backend_port}" &
backend_pid="$!"

# Give the backend a moment to start (or fail fast)
sleep 2
if ! kill -0 "${backend_pid}" 2>/dev/null; then
    wait "${backend_pid}" 2>/dev/null
    backend_rc=$?
    echo "[aieng-docker] FATAL: Backend exited immediately (code=${backend_rc})"
    echo "[aieng-docker] Check that /data is writable and build123d imports work"
    exit ${backend_rc:-1}
fi
echo "[aieng-docker] Backend PID ${backend_pid} started successfully"

# ----------------------------------------------------------------
# Start MCP HTTP server
# ----------------------------------------------------------------
echo "[aieng-docker] Starting MCP HTTP server on ${mcp_host}:${mcp_port}"
python -m app.mcp_server --http --host "${mcp_host}" --port "${mcp_port}" &
mcp_pid="$!"

sleep 2
if ! kill -0 "${mcp_pid}" 2>/dev/null; then
    wait "${mcp_pid}" 2>/dev/null
    mcp_rc=$?
    echo "[aieng-docker] FATAL: MCP server exited immediately (code=${mcp_rc})"
    echo "[aieng-docker] Shutting down backend and exiting..."
    shutdown
    exit ${mcp_rc:-1}
fi
echo "[aieng-docker] MCP server PID ${mcp_pid} started successfully"

echo "[aieng-docker] Both services are running"
echo "[aieng-docker] Workbench UI:   http://localhost:${backend_port}/app/"
echo "[aieng-docker] MCP SSE:        http://localhost:${mcp_port}/sse"
echo "[aieng-docker] Data volume:    ${AIENG_PLATFORM_DATA}"
echo "[aieng-docker] Health check:   http://localhost:${backend_port}/api/health"

# ----------------------------------------------------------------
# Health monitor — exit (so Docker restarts) when either process dies
# ----------------------------------------------------------------
while true; do
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    wait "${backend_pid}" 2>/dev/null
    rc=$?
    echo "[aieng-docker] FATAL: Backend (PID ${backend_pid}) died with exit code ${rc}"
    shutdown
    exit ${rc:-1}
  fi
  if ! kill -0 "${mcp_pid}" 2>/dev/null; then
    wait "${mcp_pid}" 2>/dev/null
    rc=$?
    echo "[aieng-docker] FATAL: MCP server (PID ${mcp_pid}) died with exit code ${rc}"
    shutdown
    exit ${rc:-1}
  fi
  sleep 2
done
