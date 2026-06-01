"""MCP tool request/response models for the .aieng patch bridge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.tool_contracts import ClaimPolicy


class AiengParsePatchRequest(BaseModel):
    """Request for aieng_parse_patch."""

    model_config = ConfigDict(extra="forbid")

    package_path: str | None = None
    patch_path: str | None = None
    patch_json: dict[str, Any] | None = None


class AiengExecutePatchRequest(BaseModel):
    """Request for aieng_execute_patch."""

    model_config = ConfigDict(extra="forbid")

    package_path: str | None = None
    patch_path: str | None = None
    patch_json: dict[str, Any] | None = None
    persist_to_aieng: bool = False
    dry_run: bool = False
