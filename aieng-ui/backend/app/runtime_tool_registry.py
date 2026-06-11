"""Registration of app-scoped MCP/runtime tool handlers.

Tool implementations are split into domain-focused submodules so the registry
stays composable and each domain can evolve independently.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from typing import Any

from .legacy_app_symbols import sync_main_symbols
from .logging_utils import log_exception

LOGGER = logging.getLogger("app.app_factory")


def _split_ccx_cmd(command: str, *, platform: str | None = None) -> list[str]:
    """Split an operator-provided ccx command into subprocess argv."""
    import shlex

    platform = platform or os.name
    parts = shlex.split(command, posix=platform != "nt")
    if platform == "nt":
        parts = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {"'", '"'} else part
            for part in parts
        ]
    return parts


def _resolve_ccx_cmd() -> list[str] | None:
    """Resolve the CalculiX (ccx) command, respecting AIENG_CCX_CMD.

    Returns a list of command parts (e.g. ["/usr/bin/ccx"] or
    ["conda", "run", "-n", "calculix-env", "ccx"]) when ccx is available,
    or None when it cannot be found.
    """
    ccx_env = os.environ.get("AIENG_CCX_CMD")
    if ccx_env:
        try:
            parts = _split_ccx_cmd(ccx_env)
        except ValueError:
            return None
        if parts and shutil.which(parts[0]):
            return parts
        return None
    for candidate in ("ccx", "ccx_linux", "ccx2.21", "ccx_static"):
        path = shutil.which(candidate)
        if path:
            return [path]
    return None


@dataclass(frozen=True)
class RuntimeToolHandlers:
    apply_shape_ir_patch: Any
    derive_topology_optimization_problem: Any
    run_topology_optimization: Any
    writeback_topology_optimization: Any
    run_assembly_topology_optimization: Any


def register_runtime_tools(*, active_settings: Any, app_context: Any) -> RuntimeToolHandlers:
    """Orchestrate domain-specific runtime tool registrations."""
    from . import runtime as _rt
    from . import runtime_tools
    from .runtime_tool_schemas import get_schema as _schema

    from .runtime_registry import aieng as _aieng
    from .runtime_registry import cad as _cad
    from .runtime_registry import cae as _cae
    from .runtime_registry import opt as _opt
    from .runtime_registry import standards as _standards

    aieng_handlers = _aieng.register_aieng_tools(_rt, active_settings, app_context, _schema)
    _cad.register_cad_tools(_rt, active_settings, app_context, _schema)
    _cae.register_cae_tools(_rt, active_settings, app_context, _schema)
    opt_handlers = _opt.register_opt_tools(_rt, active_settings, app_context, _schema)
    _standards.register_standards_tools(_rt, active_settings, app_context, _schema)



    runtime_tools.register_engineering_template_tools(_rt, active_settings)

    return RuntimeToolHandlers(
        apply_shape_ir_patch=aieng_handlers["apply_shape_ir_patch"],
        derive_topology_optimization_problem=opt_handlers["derive_topology_optimization_problem"],
        run_topology_optimization=opt_handlers["run_topology_optimization"],
        writeback_topology_optimization=opt_handlers["writeback_topology_optimization"],
        run_assembly_topology_optimization=opt_handlers["run_assembly_topology_optimization"],
    )
