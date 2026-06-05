#!/usr/bin/env bash
# Post-create script for aieng devcontainer
# Runs once after the container is created

set -euo pipefail

echo "[aieng-devcontainer] Setting up aieng workspace..."

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Install Python backend dependencies
echo "[aieng-devcontainer] Installing backend dependencies..."
cd "$REPO_ROOT/aieng-ui/backend"
pip install -e ".[dev]" 2>&1 | tail -5

# Install build123d (core CAD dependency)
echo "[aieng-devcontainer] Installing build123d..."
pip install build123d 2>&1 | tail -3

# Install frontend dependencies
echo "[aieng-devcontainer] Installing frontend dependencies..."
cd "$REPO_ROOT/aieng-ui/frontend"
npm install 2>&1 | tail -5

# Install aieng core library
echo "[aieng-devcontainer] Installing aieng core library..."
cd "$REPO_ROOT/aieng"
pip install -e ".[dev]" 2>&1 | tail -5 || pip install -e . 2>&1 | tail -5

echo ""
echo "============================================"
echo "  aieng devcontainer setup complete!"
echo "============================================"
echo ""
echo "To start the workbench: make dev"
echo "Backend API docs: http://localhost:8000/docs"
echo ""
