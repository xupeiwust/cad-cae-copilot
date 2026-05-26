"""Runtime configuration for the unified FreeCAD MCP server."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class FreecadMode(str, Enum):
    EMBEDDED = "embedded"
    XMLRPC = "xmlrpc"
    SOCKET = "socket"
    CMD = "cmd"


class TransportType(str, Enum):
    STDIO = "stdio"
    HTTP = "http"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FREECAD_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # CAD connection
    mode: FreecadMode = FreecadMode.XMLRPC
    freecad_path: str | None = None
    socket_host: str = "localhost"
    xmlrpc_port: int = 9875
    socket_port: int = 9876
    timeout_ms: int = 30000

    # MCP transport
    transport: TransportType = TransportType.STDIO
    http_port: int = 8000

    # CAE
    ccx_binary: str | None = None
    gmsh_binary: str | None = None
    solver_backend: str = "surrogate"  # "surrogate" or "freecad_fem"

    # Logging
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
