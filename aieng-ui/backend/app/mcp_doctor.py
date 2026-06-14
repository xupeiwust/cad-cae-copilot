"""Agent setup "doctor" — one-shot wiring diagnostics (#229).

A first-time user juggling agent + MCP + conda + backend needs a single
"is everything wired?" check. This module answers it portably for ANY CLI agent
(Claude Code, Codex, Cursor, Kimi, …) — not just the VSCode panel — by checking:

1. **MCP config** — does a known client config reference the ``aieng-workbench`` server?
2. **Backend** — if a backend URL is configured, is ``/api/health`` reachable and ok?
3. **Tools** — does the MCP server expose a non-empty tool set?

Each check carries a status (``ok`` / ``warn`` / ``fail`` / ``skipped``) and an
actionable fix hint. The logic is pure: the filesystem root, backend URL, tool
count, and HTTP getter are all injected, so it is fully unit-testable without a
live backend or client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

SERVER_KEY = "aieng-workbench"

# Known per-client MCP config locations, relative to a search root.
MCP_CONFIG_CANDIDATES: tuple[str, ...] = (
    ".mcp.json",          # Claude Code
    ".vscode/mcp.json",   # VS Code / GitHub Copilot
    ".cursor/mcp.json",   # Cursor
    ".codex/config.toml", # Codex (see MCP_SETUP.md)
)

# ASCII-only markers: a first-time user's console may be cp1252 (Windows), where
# unicode glyphs raise UnicodeEncodeError on print — defeating the diagnostic.
_STATUS_ICON = {"ok": "OK", "warn": "WARN", "fail": "FAIL", "skipped": "SKIP"}


def _check_mcp_config(root: Path) -> dict[str, Any]:
    found: list[str] = []
    for rel in MCP_CONFIG_CANDIDATES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            if SERVER_KEY in path.read_text(encoding="utf-8"):
                found.append(rel)
        except OSError:
            continue
    if found:
        return {
            "name": "mcp_config",
            "status": "ok",
            "detail": f"'{SERVER_KEY}' referenced in {', '.join(found)}",
            "fix": None,
        }
    return {
        "name": "mcp_config",
        "status": "warn",
        "detail": f"No MCP config referencing '{SERVER_KEY}' found under {root}",
        "fix": (
            "Add the aieng-workbench MCP server to your client config (see "
            "aieng-ui/backend/MCP_SETUP.md). For Claude Code this is .mcp.json in the repo root."
        ),
    }


def _check_backend(backend_url: str | None, http_get: Callable[[str], Any]) -> dict[str, Any]:
    if not backend_url:
        return {
            "name": "backend",
            "status": "skipped",
            "detail": "No backend URL configured — the MCP server runs self-contained (headless). Live viewer is off.",
            "fix": None,
        }
    try:
        data = http_get(f"{backend_url}/api/health")
    except Exception as exc:  # noqa: BLE001 - any transport error is a clear fail
        return {
            "name": "backend",
            "status": "fail",
            "detail": f"Backend at {backend_url} is unreachable: {type(exc).__name__}: {exc}",
            "fix": (
                "Start it: conda activate aieng311; cd aieng-ui/backend; "
                "uvicorn app.main:app --reload --port 8000 -- or omit the backend URL to run headless."
            ),
        }
    if isinstance(data, dict) and data.get("status") == "ok":
        return {
            "name": "backend",
            "status": "ok",
            "detail": (
                f"Backend healthy at {backend_url} "
                f"({data.get('runtime_tool_count', '?')} runtime tools)"
            ),
            "fix": None,
            "data": {
                "runtime_tool_count": data.get("runtime_tool_count"),
                "cad_tool_count": data.get("cad_tool_count"),
            },
        }
    return {
        "name": "backend",
        "status": "warn",
        "detail": f"Backend at {backend_url} responded without status=ok",
        "fix": "Check the backend logs; the process may be starting or unhealthy.",
    }


def _check_tools(tool_count: int | None) -> dict[str, Any]:
    if tool_count and tool_count > 0:
        return {
            "name": "tools",
            "status": "ok",
            "detail": f"MCP server exposes {tool_count} tools",
            "fix": None,
        }
    return {
        "name": "tools",
        "status": "fail",
        "detail": "MCP server registered 0 tools",
        "fix": (
            "The runtime tool registry failed to populate — reinstall the backend "
            "(pip install -e aieng-ui/backend) and check for import errors."
        ),
    }


def run_doctor(
    *,
    root: str | Path,
    backend_url: str | None,
    tool_count: int | None,
    http_get: Callable[[str], Any],
) -> dict[str, Any]:
    """Run all wiring checks and return a structured report. Pure."""
    checks = [
        _check_mcp_config(Path(root)),
        _check_backend(backend_url, http_get),
        _check_tools(tool_count),
    ]
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "ok"
    return {"overall": overall, "server_key": SERVER_KEY, "checks": checks}


def format_report(report: dict[str, Any]) -> str:
    """Render a doctor report as human-readable text with fix hints."""
    overall = str(report.get("overall", "?")).upper()
    lines = [f"aieng-workbench doctor: {overall}", ""]
    for check in report.get("checks", []):
        icon = _STATUS_ICON.get(check.get("status"), "?")
        lines.append(f"  [{icon}] {check.get('name')}: {check.get('detail')}")
        if check.get("fix"):
            lines.append(f"      -> fix: {check['fix']}")
    return "\n".join(lines)
