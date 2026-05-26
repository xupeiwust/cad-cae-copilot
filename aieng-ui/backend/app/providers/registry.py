from __future__ import annotations

from pathlib import Path
from typing import Any

from .freecad_preview import FreecadPreviewProvider
from .protocols import CadExecutionProvider


class _UnavailableCadProvider:
    """Stub provider returned when no CAD execution backend is configured.

    The build123d text-to-CAD pipeline writes its own .aieng artifacts via
    ``cad_generation.run_cad_generation`` and does not need a provider adapter.
    Legacy paths that still attempt provider operations (e.g. ``aieng.convert``
    for an externally-supplied STEP) get a structured "unavailable" response
    rather than a crash.
    """

    provider = "unavailable"

    def __init__(self, settings: Any, config: dict[str, str]) -> None:
        self._settings = settings
        self._config = config

    def probe_capabilities(self, *, whitelisted_tools: list[str]) -> dict[str, Any]:
        aieng_root = Path(str(self._config.get("aieng_root") or getattr(self._settings, "aieng_root", ""))).resolve()
        topology_requested = str(self._config.get("topology_backend") or "auto")
        return {
            "provider": self.provider,
            "available": False,
            "reason": "no CAD execution provider configured",
            "topology_backend_requested": topology_requested,
            "topology_backend_resolved": "mock" if topology_requested == "auto" else topology_requested,
            "aieng_root": str(aieng_root),
            "aieng_src_exists": (aieng_root / "src").exists(),
            "freecad_mcp_root": str(self._config.get("freecad_mcp_root") or ""),
            "freecad_mcp_src_exists": False,
            "freecad_home": str(self._config.get("freecad_home") or ""),
            "freecad_cmd": "",
            "freecad_python": "",
            "freecad_cmd_exists": False,
            "freecad_python_exists": False,
            "ready": False,
            "issues": [
                "No CAD execution provider is connected.",
                "STEP preview export is unavailable until an external CAD adapter is wired.",
            ],
            "bridge_error": self._unavailable("probe_capabilities")["message"],
            "tools": [],
            "whitelisted_tools": whitelisted_tools,
        }

    def import_step_to_package(self, *, step_path: Path, out_path: Path) -> dict[str, Any]:
        return self._unavailable("import_step_to_package")

    def enrich_package(self, *, package_path: Path, topology_backend: str) -> dict[str, Any]:
        return self._unavailable("enrich_package")

    def validate_package(self, *, package_path: Path) -> dict[str, Any]:
        return self._unavailable("validate_package")

    def package_summary_snapshot(self, *, package_path: Path) -> dict[str, Any]:
        return self._unavailable("package_summary_snapshot")

    def check_mcp_operation(
        self,
        *,
        package_path: str | None,
        payload: dict[str, Any],
        whitelisted_tools: list[str],
    ) -> dict[str, Any]:
        return self._unavailable("check_mcp_operation")

    def parse_patch_proposal(self, *, patch_json: dict[str, Any]) -> dict[str, Any]:
        return self._unavailable("parse_patch_proposal")

    def prepare_patch_preflight(
        self, *, package_path: str | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._unavailable("prepare_patch_preflight")

    def export_step_preview_to_stl(self, *, step_path: Path, stl_path: Path) -> dict[str, Any]:
        return self._unavailable("export_step_preview_to_stl")

    @staticmethod
    def _unavailable(op: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "code": "no_cad_provider",
            "operation": op,
            "message": (
                f"{op} requires a CAD execution provider, which is not configured. "
                "build123d text-to-CAD writes its own .aieng artifacts via the "
                "/api/projects/{id}/generate-cad endpoint."
            ),
        }


def get_provider(settings: Any, config: dict[str, str]) -> CadExecutionProvider:
    provider_name = str(config.get("provider") or "").strip().lower()
    if provider_name == "freecad":
        return FreecadPreviewProvider(settings, config)  # type: ignore[return-value]
    return _UnavailableCadProvider(settings, config)  # type: ignore[return-value]
