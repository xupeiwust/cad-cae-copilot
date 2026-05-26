from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

FEATURE_GRAPH_PATH = "graph/feature_graph.json"
STATUS_PATH = "validation/status.yaml"
PATCH_DIR = "ai/patches/"

_SUPPORTED_OPS = {"modify_parameter"}
_GEOMETRY_OPS = {"add_feature", "remove_feature"}
_CAE_OPS = {"assign_material", "assign_boundary_condition", "assign_load"}


class PatchNotExecutable(Exception):
    """Raised when a patch operation cannot be executed by this executor."""


class PatchExecutor:
    """Execute accepted patch proposals against a .aieng package.

    Execution has two layers:
    - Semantic layer (always): updates feature_graph.json parameters.
    - Geometry layer (future): only explicit parametric regeneration handles may
      produce modified CAD artifacts. OCP-extracted STEP measurements are not
      treated as arbitrary editable CAD history.
    """

    def execute(
        self,
        package_path: str | Path,
        patch_id: str,
        *,
        out: str | Path | None = None,
        overwrite: bool = False,
    ) -> Path:
        package_path = Path(package_path)
        if not package_path.exists():
            raise FileNotFoundError(f"package does not exist: {package_path}")
        if package_path.suffix != ".aieng":
            raise ValueError("package path must end with .aieng")

        patch_member = f"{PATCH_DIR}{patch_id}.json"
        modified_step_member = f"geometry/modified_{patch_id}.step"

        try:
            with zipfile.ZipFile(package_path, mode="r") as zf:
                names = set(zf.namelist())
                if patch_member not in names:
                    raise FileNotFoundError(f"{patch_member} not found in package")
                if FEATURE_GRAPH_PATH not in names:
                    raise FileNotFoundError(f"{FEATURE_GRAPH_PATH} not found in package")
                if modified_step_member in names and not overwrite:
                    raise FileExistsError(
                        f"{modified_step_member} already exists; use --overwrite to replace"
                    )

                patch = json.loads(zf.read(patch_member))
                feature_graph = json.loads(zf.read(FEATURE_GRAPH_PATH))
                source_step_bytes = zf.read("geometry/source.step") if "geometry/source.step" in names else None
                raw_status = zf.read(STATUS_PATH) if STATUS_PATH in names else None
                members = _read_all_members(zf, exclude={patch_member, FEATURE_GRAPH_PATH, STATUS_PATH})
        except zipfile.BadZipFile as exc:
            raise ValueError(f"package is not a valid zip archive: {package_path}") from exc

        patch_status = patch.get("status")
        if patch_status not in ("proposed", "accepted"):
            raise PatchNotExecutable(
                f"patch {patch_id} has status '{patch_status}'; "
                "only proposed or accepted patches can be executed"
            )

        operations = patch.get("operations", [])
        if not operations:
            raise PatchNotExecutable(f"patch {patch_id} has no operations to execute")

        for op in operations:
            op_type = op.get("op") or op.get("type", "")
            if op_type in _GEOMETRY_OPS:
                raise PatchNotExecutable(
                    f"operation '{op_type}' requires a geometry kernel; "
                    "only modify_parameter is supported in Phase 13B"
                )
            if op_type in _CAE_OPS:
                raise PatchNotExecutable(
                    f"operation '{op_type}' is a CAE operation; "
                    "use export-updated-deck for CAE write-back (Phase 13C)"
                )
            if op_type not in _SUPPORTED_OPS:
                raise PatchNotExecutable(
                    f"operation '{op_type}' is not executable; "
                    f"supported: {sorted(_SUPPORTED_OPS)}"
                )

        applied_ops: list[dict[str, Any]] = []
        for op in operations:
            _apply_modify_parameter(op, feature_graph)
            applied_ops.append(op)

        step_bytes, step_note, writeback_attempted = _try_step_writeback(
            source_step_bytes,
            feature_graph,
            applied_ops,
        )

        patch["status"] = "applied"
        patch["no_geometry_modified"] = step_bytes is None
        patch["execution_record"] = {
            "applied_operations": len(applied_ops),
            "feature_graph_updated": True,
            "execution_mode": "semantic_parameter_update_only" if step_bytes is None else "cad_writeback",
            "cad_writeback_attempted": writeback_attempted,
            "step_writeback": step_note,
            "step_output": modified_step_member if step_bytes else None,
            "roundtrip_required": step_bytes is not None,
        }

        updated_status: bytes | None = None
        if raw_status is not None:
            updated_status = _mark_geometry_needs_revalidation(raw_status, patch_id)

        _rewrite_package(
            package_path,
            members=members,
            feature_graph=feature_graph,
            patch=patch,
            patch_member=patch_member,
            step_bytes=step_bytes,
            step_member=modified_step_member if step_bytes else None,
            status_bytes=updated_status,
        )

        if out is not None and step_bytes is not None:
            Path(out).write_bytes(step_bytes)

        return package_path


def _apply_modify_parameter(op: dict[str, Any], feature_graph: dict[str, Any]) -> None:
    target_id = op.get("target")
    new_params = op.get("parameters") or {}

    if not target_id:
        raise PatchNotExecutable("modify_parameter operation missing 'target' field")
    if not new_params:
        raise PatchNotExecutable(f"modify_parameter on '{target_id}' has no parameters to apply")

    features = feature_graph.get("features", [])
    target = next((f for f in features if isinstance(f, dict) and f.get("id") == target_id), None)
    if target is None:
        raise PatchNotExecutable(f"feature '{target_id}' not found in feature graph")
    if not target.get("editable"):
        raise PatchNotExecutable(
            f"feature '{target_id}' has editable=false; modify_parameter is not permitted"
        )

    existing_params = target.get("parameters") or {}
    for param_name, new_value in new_params.items():
        if param_name not in existing_params:
            raise PatchNotExecutable(
                f"feature '{target_id}' does not have parameter '{param_name}'; "
                f"available parameters: {sorted(existing_params.keys())}"
            )
        existing_params[param_name] = new_value

    target["parameters"] = existing_params
    target["parameter_source"] = "user_provided"
    target["parameter_confidence"] = "medium"
    target["editability"] = target.get("editability", "semantic_only")
    target["writeback_strategy"] = target.get("writeback_strategy", "semantic_parameter_update_only")
    target.setdefault(
        "editability_reason",
        "Semantic parameter updated from patch; CAD write-back requires an explicit executable source.",
    )


def _try_step_writeback(
    source_step_bytes: bytes | None,
    feature_graph: dict[str, Any],
    applied_ops: list[dict[str, Any]],
) -> tuple[bytes | None, str, bool]:
    if source_step_bytes is None:
        return None, "no_source_step_in_package", False

    executable_features = {
        op["target"]
        for op in applied_ops
        if _feature_has_executable_cad_writeback(feature_graph, op.get("target", ""))
    }
    if not executable_features:
        return None, (
            "semantic_parameter_update_only_no_cad_writeback_handle; "
            "mock/ocp_extracted parameters are not treated as editable CAD history"
        ), False

    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        return None, "cadquery_not_available_install_cadquery_for_regeneration_writeback", True

    step_bytes = _run_cadquery_regeneration(feature_graph, applied_ops)
    if step_bytes is not None:
        return step_bytes, "cadquery_parametric_regeneration_ok", True
    return None, "cadquery_regeneration_no_supported_feature_type_for_applied_ops", True


_CADQUERY_SUPPORTED_TYPES = frozenset({
    "base_plate_candidate",
    "base_plate",
    "flange",
    "flange_candidate",
})


def _run_cadquery_regeneration(
    feature_graph: dict[str, Any],
    applied_ops: list[dict[str, Any]],
) -> bytes | None:
    """Attempt CadQuery parametric regeneration for supported feature types.

    Returns STEP bytes on success, None if no supported feature type was found.
    Only called when CadQuery is already confirmed available.
    """
    import cadquery as cq
    import tempfile

    features = {f["id"]: f for f in feature_graph.get("features", []) if isinstance(f, dict) and f.get("id")}

    for op in applied_ops:
        target_id = op.get("target", "")
        feature = features.get(target_id)
        if feature is None:
            continue
        feature_type = feature.get("type", "")
        if feature_type not in _CADQUERY_SUPPORTED_TYPES:
            continue

        params = feature.get("parameters", {})
        if feature_type in {"base_plate_candidate", "base_plate"}:
            length = float(params.get("length_mm", params.get("length", 200)))
            width = float(params.get("width_mm", params.get("width", 100)))
            height = float(params.get("height_mm", params.get("height", 20)))
            result = cq.Workplane("XY").box(length, width, height)
        elif feature_type in {"flange", "flange_candidate"}:
            diameter = float(
                params.get(
                    "outer_diameter_mm",
                    params.get("diameter_mm", params.get("diameter", 80)),
                )
            )
            thickness = float(params.get("thickness_mm", params.get("height_mm", params.get("height", 12))))
            result = cq.Workplane("XY").circle(max(diameter / 2.0, 1.0)).extrude(max(thickness, 1.0))
        else:
            continue

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as fh:
            tmp_path = Path(fh.name)
        try:
            result.val().exportStep(str(tmp_path))
            return tmp_path.read_bytes()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    return None


def _feature_has_executable_cad_writeback(feature_graph: dict[str, Any], feature_id: str) -> bool:
    features = feature_graph.get("features", [])
    target = next((f for f in features if isinstance(f, dict) and f.get("id") == feature_id), None)
    if target is None:
        return False
    return (
        target.get("editability") == "executable_by_regeneration"
        and target.get("writeback_strategy") == "cadquery_regeneration"
    )


def _mark_geometry_needs_revalidation(raw_status: bytes, patch_id: str) -> bytes:
    try:
        status = yaml.safe_load(raw_status)
    except Exception:
        return raw_status
    if not isinstance(status, dict):
        return raw_status
    geometry = status.setdefault("geometry_status", {})
    if isinstance(geometry, dict):
        geometry["patch_applied"] = patch_id
        geometry["revalidation_required"] = True
    patch_status = status.setdefault("patch_status", {})
    if isinstance(patch_status, dict):
        patch_status["last_applied_patch"] = patch_id
        patch_status["geometry_modified_by_patch"] = False
        patch_status["parameters_updated_by_patch"] = True
    return yaml.dump(status, default_flow_style=False, allow_unicode=True).encode()


def _read_all_members(
    package: zipfile.ZipFile,
    exclude: set[str],
) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in exclude or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package(
    path: Path,
    *,
    members: list[tuple[zipfile.ZipInfo, bytes]],
    feature_graph: dict[str, Any],
    patch: dict[str, Any],
    patch_member: str,
    step_bytes: bytes | None,
    step_member: str | None,
    status_bytes: bytes | None,
) -> None:
    feature_graph_json = (json.dumps(feature_graph, indent=2, sort_keys=True) + "\n").encode()
    patch_json = (json.dumps(patch, indent=2, sort_keys=True) + "\n").encode()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp_path = Path(fh.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for info, data in members:
                zf.writestr(info, data)
            zf.writestr(FEATURE_GRAPH_PATH, feature_graph_json)
            zf.writestr(patch_member, patch_json)
            if step_bytes is not None and step_member is not None:
                zf.writestr(step_member, step_bytes)
            if status_bytes is not None:
                zf.writestr(STATUS_PATH, status_bytes)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def apply_patch_package(
    package_path: str | Path,
    patch_id: str,
    *,
    out: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    return PatchExecutor().execute(package_path, patch_id, out=out, overwrite=overwrite)
