from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


class Build123dPreviewProvider:
    """Default CAD preview provider backed by build123d/OCP.

    The agent-driven modelling path already creates STEP/STL/GLB assets via
    build123d. This provider keeps imported STEP preview generation on the same
    CAD-neutral stack instead of routing the default runtime through FreeCADCmd.
    """

    provider = "build123d"

    def __init__(self, settings: Any, config: dict[str, str]) -> None:
        self._settings = settings
        self._config = config

    def probe_capabilities(self, *, whitelisted_tools: list[str]) -> dict[str, Any]:
        aieng_root = Path(str(self._config.get("aieng_root") or getattr(self._settings, "aieng_root", ""))).resolve()
        topology_requested = str(self._config.get("topology_backend") or "auto")
        topology_resolved = self._resolve_topology_backend(topology_requested)
        build123d_available, build123d_error = self._module_importable("build123d")
        ocp_available, ocp_error = self._module_importable("OCP.STEPControl")

        issues: list[str] = []
        if build123d_available:
            issues.append("build123d ready for STEP preview export and agent CAD execution.")
        else:
            issues.append(f"build123d import failed; STEP preview export is unavailable. {build123d_error}")
        if not ocp_available:
            issues.append(f"OCP STEP runtime is unavailable; topology extraction will degrade to mock mode. {ocp_error}")

        return {
            "provider": self.provider,
            "available": build123d_available,
            "reason": None if build123d_available else "build123d import failed",
            "topology_backend_requested": topology_requested,
            "topology_backend_resolved": topology_resolved,
            "aieng_root": str(aieng_root),
            "aieng_src_exists": (aieng_root / "src").exists(),
            "freecad_mcp_root": str(self._config.get("freecad_mcp_root") or ""),
            "freecad_mcp_src_exists": False,
            "freecad_home": str(self._config.get("freecad_home") or ""),
            "freecad_cmd": "",
            "freecad_python": "",
            "freecad_cmd_exists": False,
            "freecad_python_exists": False,
            "build123d_available": build123d_available,
            "ocp_available": ocp_available,
            "ready": build123d_available,
            "issues": issues,
            "bridge_error": None if build123d_available else build123d_error,
            "tools": ["cad_export_stl"] if build123d_available else [],
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
        if not step_path.exists():
            return {
                "status": "error",
                "code": "missing_source_step",
                "message": f"Source STEP not found: {step_path}",
            }

        try:
            import build123d as b123d
        except Exception as exc:
            return {
                "status": "unavailable",
                "code": "build123d_missing",
                "message": f"build123d is not installed: {exc}",
            }

        try:
            import_fn = getattr(b123d, "import_step", None)
            if import_fn is None:
                import_fn = getattr(getattr(b123d, "Shape", None), "import_step", None)
            if import_fn is None:
                return {
                    "status": "error",
                    "code": "import_step_missing",
                    "message": "build123d has no import_step API.",
                }

            shape = import_fn(str(step_path))
            stl_path.parent.mkdir(parents=True, exist_ok=True)
            export_fn = getattr(b123d, "export_stl", None)
            if export_fn is not None:
                export_fn(shape, str(stl_path))
            else:
                method = getattr(shape, "export_stl", None)
                if method is None:
                    return {
                        "status": "error",
                        "code": "export_stl_missing",
                        "message": "build123d has no export_stl API.",
                    }
                method(str(stl_path))
        except Exception as exc:
            return {
                "status": "error",
                "code": "build123d_step_export_failed",
                "message": f"{type(exc).__name__}: {exc}",
            }

        return {
            "status": "ok",
            "provider": self.provider,
            "object_count": 1,
            "stl_path": str(stl_path),
        }

    @staticmethod
    def _resolve_topology_backend(requested: str | None) -> str:
        value = str(requested or "auto").strip().lower()
        if value != "auto":
            return value
        return "occ" if Build123dPreviewProvider._module_importable("OCP.STEPControl")[0] else "mock"

    @staticmethod
    def _module_importable(module_name: str) -> tuple[bool, str | None]:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, None

    @staticmethod
    def _unavailable(op: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "code": "build123d_preview_provider_minimal",
            "operation": op,
            "message": (
                f"{op} is not implemented in the build123d preview provider. "
                "Core package import, validation, and summaries use the .aieng bridge "
                "and zip fallback paths elsewhere in the backend."
            ),
        }
