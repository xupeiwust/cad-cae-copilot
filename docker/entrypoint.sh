#!/usr/bin/env bash
set -euo pipefail

backend_host="${AIENG_BACKEND_HOST:-0.0.0.0}"
backend_port="${AIENG_BACKEND_PORT:-8000}"
mcp_host="${AIENG_MCP_HOST:-0.0.0.0}"
mcp_port="${AIENG_MCP_PORT:-8765}"

export AIENG_PLATFORM_DATA="${AIENG_PLATFORM_DATA:-/data}"
export AIENG_ROOT="${AIENG_ROOT:-/opt/aieng/aieng}"
export AIENG_BACKEND_URL="${AIENG_BACKEND_URL:-http://127.0.0.1:${backend_port}}"
export AIENG_MCP_MANAGED_APPROVAL="${AIENG_MCP_MANAGED_APPROVAL:-1}"

mkdir -p "${AIENG_PLATFORM_DATA}"

backend_pid=""
mcp_pid=""

shutdown() {
  echo "[aieng-docker] Shutting down..."
  if [[ -n "${mcp_pid}" ]] && kill -0 "${mcp_pid}" 2>/dev/null; then
    kill "${mcp_pid}" 2>/dev/null || true
  fi
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap shutdown SIGINT SIGTERM EXIT

echo "[aieng-docker] Starting backend on ${backend_host}:${backend_port}"
python -m uvicorn app.main:app --host "${backend_host}" --port "${backend_port}" &
backend_pid="$!"

echo "[aieng-docker] Starting MCP HTTP server on ${mcp_host}:${mcp_port}"
python -m app.mcp_server --http --host "${mcp_host}" --port "${mcp_port}" &
mcp_pid="$!"

echo "[aieng-docker] Workbench UI: http://localhost:${backend_port}/app/"
echo "[aieng-docker] MCP SSE endpoint: http://localhost:${mcp_port}/sse"
echo "[aieng-docker] Data volume: ${AIENG_PLATFORM_DATA}"

while true; do
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    wait "${backend_pid}"
    exit $?
  fi
  if ! kill -0 "${mcp_pid}" 2>/dev/null; then
    wait "${mcp_pid}"
    exit $?
  fi
  sleep 2
done
