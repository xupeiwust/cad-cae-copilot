"""Parametric CAD + FEA setup template authoring (v0.34).

Generates *draft* engineering setup artifacts from a narrow set of controlled
templates. The drafts are reviewable inputs, not executable models:

  - the CAD script preview is inert Python text with an explicit safety header;
  - the FEA setup draft is structured JSON, not a solver input deck;
  - design target suggestions are written to a separate "suggestions" file
    and never overwrite the existing ``task/design_targets.yaml`` artifact;
  - nothing in this module runs Gmsh, CalculiX, or any subprocess.

The module exposes two pure entry points consumed by the API surface in
``app_factory``:

  - :func:`preview_template` — read-only.  Validates user parameters, renders
    the draft, returns it.  Never writes to the ``.aieng`` package.
  - :func:`save_template_draft` — explicit user action.  Writes only the four
    draft artifacts listed in :data:`_DRAFT_ARTIFACT_PATHS`; never edits CAD,
    never touches design targets, never runs a tool.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import HTTPException

from .config import Settings
from .copilot_loop import _resolve_package
from .design_targets import get_design_targets, save_design_targets, validate_design_targets_document
from .project_io import (
    REVALIDATION_STATUS_PATH,
    _GEOMETRY_STALE_ARTIFACTS,
    _record_geometry_edit_in_package,
    write_artifact_to_package,
)

SCHEMA_VERSION = "0.1"
TEMPLATE_CATEGORY = "structural"
CLAIM_ADVANCEMENT: Literal["none"] = "none"

CLAIM_BOUNDARY = (
    "Engineering template output is a reviewable draft only. It does not "
    "certify the design, does not run CAD/mesh/solver tools, and does not "
    "advance engineering claims. A qualified engineer must review the draft "
    "before it is used as the basis for any decision."
)

_SAFETY_NOTE = (
    "Template-generated CAD script and FEA setup are drafts. They are not "
    "executed by AIENG. The user must review the draft and explicitly "
    "proceed through the existing CAD edit and structural solver run "
    "workflows, which remain approval-gated."
)

_DRAFT_DIR = "task"
DRAFT_MANIFEST_PATH = f"{_DRAFT_DIR}/engineering_setup_draft.json"
DRAFT_CAD_SCRIPT_PATH = f"{_DRAFT_DIR}/cad_template_preview.py"
DRAFT_FEA_SETUP_PATH = f"{_DRAFT_DIR}/fea_setup_draft.json"
DRAFT_TARGET_SUGGESTIONS_PATH = f"{_DRAFT_DIR}/design_targets_suggestions.yaml"
GENERATED_CAD_FIXTURE_PATH = "geometry/template_cad_fixture.json"

_DRAFT_ARTIFACT_PATHS: tuple[str, ...] = (
    DRAFT_MANIFEST_PATH,
    DRAFT_CAD_SCRIPT_PATH,
    DRAFT_FEA_SETUP_PATH,
    DRAFT_TARGET_SUGGESTIONS_PATH,
)

# Paths the save-draft step MUST NOT touch. Defensive list — the writer below
# only ever writes the four paths above, but the test suite cross-checks that
# none of these names appear among newly created package members after a save.
PROTECTED_PATHS: tuple[str, ...] = (
    "task/design_targets.yaml",
    "task/design_targets.yml",
    "task/design_targets.json",
)

ADOPTED_TARGETS_NOTE = (
    "Template target suggestions were explicitly adopted by the user. They are "
    "review metadata only: adoption does not run CAD/mesh/solver tools, does "
    "not certify the design, and does not advance engineering claims."
)

CAD_FIXTURE_NOTE = (
    "Template CAD fixture generation is an explicit, approval-required package "
    "write. It creates deterministic geometry metadata only; it does not run "
    "CadQuery/Gmsh/CalculiX, does not create a STEP/FCStd file, and "
    "does not advance engineering claims."
)

_PARAM_KIND = ("number", "string", "select", "boolean")

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_SUPPORTED_LENGTH_UNITS = ("mm",)
_SUPPORTED_FORCE_UNITS = ("N",)
_SUPPORTED_STRESS_UNITS = ("MPa",)


# ── material library ──────────────────────────────────────────────────────────


_MATERIALS: dict[str, dict[str, Any]] = {
    "aluminum_6061_t6": {
        "name": "Aluminum 6061-T6",
        "youngs_modulus_MPa": 69000.0,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2700.0,
        "yield_stress_MPa": 276.0,
    },
    "steel_s235": {
        "name": "Steel S235",
        "youngs_modulus_MPa": 210000.0,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7850.0,
        "yield_stress_MPa": 235.0,
    },
    "stainless_304": {
        "name": "Stainless Steel 304",
        "youngs_modulus_MPa": 193000.0,
        "poisson_ratio": 0.29,
        "density_kg_m3": 8000.0,
        "yield_stress_MPa": 215.0,
    },
}

_MATERIAL_CHOICES = sorted(_MATERIALS.keys())


# ── template definitions ──────────────────────────────────────────────────────


def _param(
    id_: str,
    *,
    label: str,
    kind: str,
    description: str,
    unit: str | None = None,
    default: Any = None,
    min_: float | None = None,
    max_: float | None = None,
    required: bool = True,
    choices: list[str] | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "id": id_,
        "label": label,
        "kind": kind,
        "unit": unit,
        "default": default,
        "min": min_,
        "max": max_,
        "required": required,
        "description": description,
    }
    if choices is not None:
        spec["choices"] = list(choices)
    return spec


_TEMPLATES: dict[str, dict[str, Any]] = {
    "cantilever_beam": {
        "id": "cantilever_beam",
        "label": "Cantilever beam (rectangular)",
        "description": (
            "Rectangular cantilever beam fixed at one end and loaded transversely "
            "at the free end. Suitable for tip-deflection and root-stress sizing studies."
        ),
        "category": TEMPLATE_CATEGORY,
        "parameters": [
            _param("length_mm", label="Length", kind="number", unit="mm",
                   default=200.0, min_=1.0, max_=5000.0,
                   description="Beam length along the longitudinal (x) axis."),
            _param("width_mm", label="Width", kind="number", unit="mm",
                   default=20.0, min_=0.1, max_=1000.0,
                   description="Cross-section width along z."),
            _param("height_mm", label="Height", kind="number", unit="mm",
                   default=10.0, min_=0.1, max_=1000.0,
                   description="Cross-section height along y."),
            _param("material", label="Material", kind="select",
                   default="aluminum_6061_t6", choices=_MATERIAL_CHOICES,
                   description="Material from the controlled library."),
            _param("tip_load_N", label="Tip load (downward)", kind="number", unit="N",
                   default=1000.0, min_=0.0, max_=1.0e7,
                   description="Concentrated transverse load at the free end (-y)."),
            _param("allowable_stress_MPa", label="Allowable stress", kind="number", unit="MPa",
                   default=200.0, min_=0.0, max_=2000.0, required=False,
                   description="Allowable von Mises stress used for the suggested target."),
            _param("max_displacement_mm", label="Max allowable tip displacement",
                   kind="number", unit="mm", default=5.0, min_=0.0, max_=1000.0,
                   required=False,
                   description="Suggested displacement target at the loaded tip."),
        ],
        "geometry_kind": "box",
        "boundary_conditions": [
            {"id": "fixed_root", "type": "fixed", "region": "x_min_face",
             "description": "Beam fixed against translation and rotation at x_min."}
        ],
        "loads_template": [
            {"id": "tip_force", "type": "force", "region": "x_max_face",
             "direction": [0, -1, 0], "magnitude_param": "tip_load_N", "unit": "N"}
        ],
    },
    "plate_with_hole": {
        "id": "plate_with_hole",
        "label": "Plate with central hole (tensile)",
        "description": (
            "Rectangular plate with a centred circular hole, loaded in uniaxial tension. "
            "Classical stress-concentration study; treat the resulting stress as a "
            "concentration-amplified value and review accordingly."
        ),
        "category": TEMPLATE_CATEGORY,
        "parameters": [
            _param("length_mm", label="Length", kind="number", unit="mm",
                   default=200.0, min_=1.0, max_=5000.0,
                   description="Plate length along the loading (x) axis."),
            _param("width_mm", label="Width", kind="number", unit="mm",
                   default=100.0, min_=1.0, max_=5000.0,
                   description="Plate width along y."),
            _param("thickness_mm", label="Thickness", kind="number", unit="mm",
                   default=5.0, min_=0.1, max_=200.0,
                   description="Plate thickness along z."),
            _param("hole_diameter_mm", label="Hole diameter", kind="number", unit="mm",
                   default=20.0, min_=0.1, max_=4900.0,
                   description="Diameter of the centred through-hole."),
            _param("material", label="Material", kind="select",
                   default="steel_s235", choices=_MATERIAL_CHOICES,
                   description="Material from the controlled library."),
            _param("tensile_load_N", label="Tensile load", kind="number", unit="N",
                   default=5000.0, min_=0.0, max_=1.0e7,
                   description="Total uniaxial tensile load applied at the x_max face (+x)."),
            _param("allowable_stress_MPa", label="Allowable stress", kind="number", unit="MPa",
                   default=200.0, min_=0.0, max_=2000.0, required=False,
                   description="Allowable von Mises stress for the suggested target."),
        ],
        "geometry_kind": "plate_with_hole",
        "boundary_conditions": [
            {"id": "fixed_left", "type": "fixed", "region": "x_min_face",
             "description": "Plate clamped on the x_min face."}
        ],
        "loads_template": [
            {"id": "tensile_load", "type": "force", "region": "x_max_face",
             "direction": [1, 0, 0], "magnitude_param": "tensile_load_N", "unit": "N"}
        ],
    },
}

TEMPLATE_IDS = tuple(_TEMPLATES.keys())


# ── helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _error(code: str, message: str, *, field: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "field": field}


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None  # bools are not valid numbers here
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n):
        return None
    return n


def _validate_parameters(
    template: dict[str, Any], raw: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    raw = raw if isinstance(raw, dict) else {}
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    normalized: dict[str, Any] = {}

    known_ids = {p["id"] for p in template["parameters"]}
    for key in raw.keys():
        if not isinstance(key, str) or not _SAFE_NAME_RE.match(key):
            errors.append(_error("invalid_parameter_name",
                                 f"Parameter name {key!r} is not allowed.",
                                 field=str(key)))
            continue
        if key not in known_ids:
            warnings.append(f"Unknown parameter {key!r} ignored.")

    for spec in template["parameters"]:
        pid = spec["id"]
        value = raw.get(pid, spec.get("default"))

        if value is None and spec.get("required"):
            # Treat an explicit `None` for a required field the same as a
            # missing key: both mean "the user has not supplied a value".
            errors.append(_error("missing_required", f"Required parameter '{pid}' is missing.", field=pid))
            continue
        if value is None and not spec.get("required"):
            continue

        kind = spec["kind"]
        if kind == "number":
            n = _coerce_number(value)
            if n is None:
                errors.append(_error("invalid_value", f"Parameter '{pid}' must be a finite number.", field=pid))
                continue
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and n < lo:
                errors.append(_error("out_of_range",
                                     f"Parameter '{pid}'={n} is below the minimum {lo}.",
                                     field=pid))
                continue
            if hi is not None and n > hi:
                errors.append(_error("out_of_range",
                                     f"Parameter '{pid}'={n} is above the maximum {hi}.",
                                     field=pid))
                continue
            normalized[pid] = n
        elif kind == "select":
            choices = spec.get("choices") or []
            if value not in choices:
                errors.append(_error("invalid_choice",
                                     f"Parameter '{pid}' must be one of: {', '.join(choices)}.",
                                     field=pid))
                continue
            normalized[pid] = value
        elif kind == "string":
            if not isinstance(value, str) or not _SAFE_NAME_RE.match(value):
                errors.append(_error("invalid_value",
                                     f"Parameter '{pid}' must be a short safe string.",
                                     field=pid))
                continue
            normalized[pid] = value
        elif kind == "boolean":
            if not isinstance(value, bool):
                errors.append(_error("invalid_value", f"Parameter '{pid}' must be true or false.", field=pid))
                continue
            normalized[pid] = value
        else:
            errors.append(_error("unsupported_kind", f"Parameter '{pid}' has unsupported kind {kind!r}.", field=pid))

    # Cross-parameter sanity for the templates we ship.
    if template["id"] == "plate_with_hole" and not errors:
        length = normalized.get("length_mm")
        width = normalized.get("width_mm")
        hole = normalized.get("hole_diameter_mm")
        thickness = normalized.get("thickness_mm")
        if hole is not None and width is not None and hole >= width:
            errors.append(_error("inconsistent_geometry",
                                 f"hole_diameter_mm ({hole}) must be smaller than width_mm ({width}).",
                                 field="hole_diameter_mm"))
        if hole is not None and length is not None and hole >= length:
            errors.append(_error("inconsistent_geometry",
                                 f"hole_diameter_mm ({hole}) must be smaller than length_mm ({length}).",
                                 field="hole_diameter_mm"))
        if thickness is not None and hole is not None and thickness > hole * 5:
            warnings.append(
                f"thickness_mm ({thickness}) is large relative to hole_diameter_mm ({hole}); "
                "plane-stress stress-concentration estimates may not apply."
            )

    return normalized, errors, warnings


# ── renderers ────────────────────────────────────────────────────────────────


_CAD_SAFETY_HEADER = (
    "# Generated draft only. Not executed by AIENG in this step.\n"
    "# Requires engineering review before use.\n"
    "# Source: AIENG engineering_templates v{schema}.\n"
    "# Template: {template_id}.\n"
    "# Generated at: {generated_at}.\n"
    "# This script is inert text; no Python is executed by AIENG when generating\n"
    "# this preview. A qualified engineer must open and run it explicitly\n"
    "# inside a sandboxed CAD environment.\n"
).rstrip()


def _format_float(value: float) -> str:
    text = repr(float(value))
    # `repr(1.0) == "1.0"` is fine; cap excessive precision noise.
    return text


def _render_cad_script(template_id: str, params: dict[str, Any]) -> str:
    header = _CAD_SAFETY_HEADER.format(
        schema=SCHEMA_VERSION, template_id=template_id, generated_at=_now_iso()
    )
    if template_id == "cantilever_beam":
        body = (
            "\n"
            "import cadquery as cq  # not imported by AIENG; placeholder for the reviewer\n"
            "\n"
            f"length_mm = {_format_float(params['length_mm'])}\n"
            f"width_mm = {_format_float(params['width_mm'])}\n"
            f"height_mm = {_format_float(params['height_mm'])}\n"
            "\n"
            "beam = (\n"
            "    cq.Workplane('XY')\n"
            "      .box(length_mm, width_mm, height_mm, centered=(False, True, True))\n"
            ")\n"
            "\n"
            "# Suggested reviewer actions:\n"
            "#   * sanity-check dimensions against the engineering intent\n"
            "#   * export to STEP only after explicit review\n"
            "#   * do NOT auto-feed this into the AIENG runtime; use the\n"
            "#     existing CAD edit / structural solver approval gates\n"
        )
        return header + body
    if template_id == "plate_with_hole":
        body = (
            "\n"
            "import cadquery as cq  # not imported by AIENG; placeholder for the reviewer\n"
            "\n"
            f"length_mm = {_format_float(params['length_mm'])}\n"
            f"width_mm = {_format_float(params['width_mm'])}\n"
            f"thickness_mm = {_format_float(params['thickness_mm'])}\n"
            f"hole_diameter_mm = {_format_float(params['hole_diameter_mm'])}\n"
            "\n"
            "plate = (\n"
            "    cq.Workplane('XY')\n"
            "      .box(length_mm, width_mm, thickness_mm, centered=(False, True, True))\n"
            "      .faces('>Z').workplane()\n"
            "      .center(length_mm / 2.0, 0)\n"
            "      .hole(hole_diameter_mm)\n"
            ")\n"
            "\n"
            "# Suggested reviewer actions:\n"
            "#   * verify hole placement against the engineering intent\n"
            "#   * note the stress concentration around the hole when reviewing FEA\n"
            "#   * do NOT auto-feed this into the AIENG runtime\n"
        )
        return header + body
    raise HTTPException(status_code=500, detail=f"unknown template {template_id}")


def _render_fea_setup_draft(template_id: str, params: dict[str, Any]) -> dict[str, Any]:
    material_id = params["material"]
    material_props = _MATERIALS[material_id]
    template = _TEMPLATES[template_id]
    loads_out: list[dict[str, Any]] = []
    for load in template["loads_template"]:
        magnitude_param = load["magnitude_param"]
        loads_out.append({
            "id": load["id"],
            "type": load["type"],
            "region": load["region"],
            "direction": load["direction"],
            "magnitude": params[magnitude_param],
            "unit": load["unit"],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "template_id": template_id,
        "category": template["category"],
        "generated_at": _now_iso(),
        "material": {
            "id": material_id,
            "name": material_props["name"],
            "youngs_modulus": material_props["youngs_modulus_MPa"],
            "youngs_modulus_unit": "MPa",
            "poisson_ratio": material_props["poisson_ratio"],
            "density": material_props["density_kg_m3"],
            "density_unit": "kg/m^3",
            "yield_stress": material_props.get("yield_stress_MPa"),
            "yield_stress_unit": "MPa",
        },
        "geometry": {
            "kind": template["geometry_kind"],
            "parameters": {k: v for k, v in params.items() if k != "material"},
        },
        "boundary_conditions": [dict(bc) for bc in template["boundary_conditions"]],
        "loads": loads_out,
        "solver_deck": {
            "generated": False,
            "note": (
                "No solver input deck is generated by the template draft. The user "
                "must compose the deck through the existing approval-gated structural "
                "solver workflow."
            ),
        },
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _render_target_suggestions(template_id: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    template = _TEMPLATES[template_id]
    material = _MATERIALS[params["material"]]
    yield_stress = material.get("yield_stress_MPa")
    allowable = params.get("allowable_stress_MPa")
    if allowable is None and yield_stress is not None:
        allowable = round(yield_stress * 0.667, 1)  # ~2/3 of yield as a soft default
    suggestions: list[dict[str, Any]] = []
    if allowable is not None:
        suggestions.append({
            "target_id": f"{template_id}_max_stress",
            "label": "Max von Mises stress (suggested)",
            "metric": "max_von_mises_stress",
            "operator": "<=",
            "value": allowable,
            "unit": "MPa",
            "priority": "high",
            "rationale": (
                f"Derived from allowable_stress_MPa ({allowable}) for material "
                f"{material['name']}. Stress targets should be reviewed against "
                "the actual failure mode and safety factor before adoption."
            ),
        })
    if template_id == "cantilever_beam":
        max_disp = params.get("max_displacement_mm")
        if max_disp is not None:
            suggestions.append({
                "target_id": "cantilever_max_tip_displacement",
                "label": "Max tip displacement (suggested)",
                "metric": "max_displacement",
                "operator": "<=",
                "value": max_disp,
                "unit": "mm",
                "priority": "medium",
                "rationale": (
                    "Tip displacement bound provided in the template draft. Replace "
                    "with the project's actual stiffness requirement before adopting."
                ),
            })
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "template_id": template_id,
            "generated_at": _now_iso(),
            **s,
        }
        for s in suggestions
    ]


# ── public API used by app_factory endpoints ─────────────────────────────────


def _template_summary(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": template["id"],
        "label": template["label"],
        "description": template["description"],
        "category": template["category"],
        "parameter_count": len(template["parameters"]),
        "outputs": {
            "cad_script_preview": True,
            "fea_setup_draft": True,
            "design_target_suggestions": True,
        },
        "safety_note": _SAFETY_NOTE,
        "claim_advancement": CLAIM_ADVANCEMENT,
    }


def _template_detail(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **_template_summary(template),
        "parameters": [
            {k: v for k, v in p.items() if v is not None or k in {"unit", "default", "min", "max"}}
            for p in template["parameters"]
        ],
        "materials": [
            {"id": mid, **{k: v for k, v in props.items()}}
            for mid, props in _MATERIALS.items()
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def list_engineering_templates() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "templates": [_template_summary(t) for t in _TEMPLATES.values()],
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def get_engineering_template(template_id: str) -> dict[str, Any]:
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown template '{template_id}'")
    return _template_detail(template)


def _build_preview_response(
    template: dict[str, Any],
    project_id: str,
    raw_params: dict[str, Any] | None,
    *,
    package_path: Path | None,
) -> dict[str, Any]:
    normalized, errors, warnings = _validate_parameters(template, raw_params)
    response: dict[str, Any] = {
        "ok": not errors,
        "template_id": template["id"],
        "project_id": project_id,
        "package_path": str(package_path) if package_path else None,
        "parameters": normalized,
        "errors": errors,
        "warnings": warnings,
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
        "safety_note": _SAFETY_NOTE,
    }
    if errors:
        return response
    response["cad_script_preview"] = _render_cad_script(template["id"], normalized)
    response["fea_setup_draft"] = _render_fea_setup_draft(template["id"], normalized)
    response["design_target_suggestions"] = _render_target_suggestions(template["id"], normalized)
    return response


def preview_template(
    settings: Settings, project_id: str, template_id: str, payload: dict[str, Any] | None
) -> dict[str, Any]:
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown template '{template_id}'")
    package_path: Path | None
    try:
        package_path = _resolve_package(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            package_path = None
        else:
            raise
    body = payload if isinstance(payload, dict) else {}
    raw_params = body.get("parameters") if isinstance(body.get("parameters"), dict) else body
    return _build_preview_response(template, project_id, raw_params, package_path=package_path)


def _write_draft_artifacts(
    package_path: Path,
    *,
    manifest: dict[str, Any],
    cad_script: str,
    fea_setup: dict[str, Any],
    target_suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Atomically write the four draft artifacts. No other files are touched."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="aieng_template_draft_"))
    written: list[dict[str, Any]] = []
    try:
        manifest_tmp = tmp_dir / "manifest.json"
        manifest_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        cad_tmp = tmp_dir / "cad.py"
        cad_tmp.write_text(cad_script, encoding="utf-8")
        fea_tmp = tmp_dir / "fea.json"
        fea_tmp.write_text(json.dumps(fea_setup, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        suggestions_doc = {
            "schema_version": SCHEMA_VERSION,
            "template_id": manifest["template_id"],
            "generated_at": manifest["generated_at"],
            "suggestions": target_suggestions,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
            "note": (
                "Suggested targets only. Adopt by editing the existing "
                "task/design_targets.yaml via the Design Targets card; this file "
                "is never read by the target comparison engine."
            ),
        }
        suggestions_tmp = tmp_dir / "suggestions.yaml"
        suggestions_tmp.write_text(yaml.safe_dump(suggestions_doc, sort_keys=False), encoding="utf-8")

        for artifact_path, source in (
            (DRAFT_MANIFEST_PATH, manifest_tmp),
            (DRAFT_CAD_SCRIPT_PATH, cad_tmp),
            (DRAFT_FEA_SETUP_PATH, fea_tmp),
            (DRAFT_TARGET_SUGGESTIONS_PATH, suggestions_tmp),
        ):
            written.append(
                write_artifact_to_package(package_path, artifact_path, source, overwrite=True)
            )
    finally:
        for child in tmp_dir.glob("*"):
            try:
                child.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
    return written


def save_template_draft(
    settings: Settings, project_id: str, template_id: str, payload: dict[str, Any] | None
) -> dict[str, Any]:
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown template '{template_id}'")
    try:
        package_path = _resolve_package(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "ok": False,
                "template_id": template_id,
                "project_id": project_id,
                "errors": [_error("package_not_found", "Project has no .aieng package; cannot save draft.")],
                "warnings": [],
                "claim_advancement": CLAIM_ADVANCEMENT,
                "claim_boundary": CLAIM_BOUNDARY,
            }
        raise

    body = payload if isinstance(payload, dict) else {}
    raw_params = body.get("parameters") if isinstance(body.get("parameters"), dict) else body
    preview = _build_preview_response(template, project_id, raw_params, package_path=package_path)
    if not preview["ok"]:
        return {
            "ok": False,
            "template_id": template_id,
            "project_id": project_id,
            "package_path": str(package_path),
            "errors": preview["errors"],
            "warnings": preview["warnings"],
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    fea_setup = preview["fea_setup_draft"]
    cad_script = preview["cad_script_preview"]
    suggestions = preview["design_target_suggestions"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "template_id": template_id,
        "project_id": project_id,
        "generated_at": _now_iso(),
        "parameters": preview["parameters"],
        "artifacts": {
            "cad_script_preview": DRAFT_CAD_SCRIPT_PATH,
            "fea_setup_draft": DRAFT_FEA_SETUP_PATH,
            "design_target_suggestions": DRAFT_TARGET_SUGGESTIONS_PATH,
        },
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
        "safety_note": _SAFETY_NOTE,
    }
    written = _write_draft_artifacts(
        package_path,
        manifest=manifest,
        cad_script=cad_script,
        fea_setup=fea_setup,
        target_suggestions=suggestions,
    )

    return {
        "ok": True,
        "template_id": template_id,
        "project_id": project_id,
        "package_path": str(package_path),
        "parameters": preview["parameters"],
        "warnings": preview["warnings"],
        "errors": [],
        "artifacts": written,
        "draft_paths": list(_DRAFT_ARTIFACT_PATHS),
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
        "safety_note": _SAFETY_NOTE,
    }


def _read_saved_target_suggestions(package_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read target suggestions from a saved draft artifact."""
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if DRAFT_TARGET_SUGGESTIONS_PATH not in zf.namelist():
                return [], [f"No saved target suggestions found at {DRAFT_TARGET_SUGGESTIONS_PATH}."]
            doc = yaml.safe_load(zf.read(DRAFT_TARGET_SUGGESTIONS_PATH).decode("utf-8", errors="replace"))
    except Exception as exc:
        return [], [f"Could not read saved target suggestions: {type(exc).__name__}: {exc}"]
    suggestions = doc.get("suggestions") if isinstance(doc, dict) else None
    if not isinstance(suggestions, list):
        return [], [f"{DRAFT_TARGET_SUGGESTIONS_PATH} does not contain a suggestions array."]
    return [s for s in suggestions if isinstance(s, dict)], warnings


def _normalize_suggestion_for_design_target(suggestion: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "target_id",
        "label",
        "metric",
        "operator",
        "value",
        "threshold_min",
        "threshold_max",
        "unit",
        "scope",
        "load_case_id",
        "priority",
        "rationale",
    }
    target = {k: v for k, v in suggestion.items() if k in allowed and v is not None}
    rationale = str(target.get("rationale") or "").strip()
    suffix = " Adopted from an AIENG engineering template suggestion; review before using for acceptance."
    target["rationale"] = (rationale + suffix).strip()[:500]
    target.setdefault("priority", "informational")
    return target


def adopt_template_target_suggestions(
    settings: Settings,
    project_id: str,
    template_id: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Explicitly adopt template target suggestions into task/design_targets.yaml.

    This is the v0.35 handoff from controlled template draft to the existing
    Design Targets workflow. It mutates only the design-target artifact and
    never runs CAD, mesh, solver, postprocessing, or claim updates.
    """
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown template '{template_id}'")

    try:
        package_path = _resolve_package(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "ok": False,
                "template_id": template_id,
                "project_id": project_id,
                "adopted_count": 0,
                "skipped_duplicate_ids": [],
                "errors": [_error("package_not_found", "Project has no .aieng package; cannot adopt targets.")],
                "warnings": [],
                "claim_advancement": CLAIM_ADVANCEMENT,
                "claim_boundary": CLAIM_BOUNDARY,
            }
        raise

    body = payload if isinstance(payload, dict) else {}
    raw_suggestions = body.get("suggestions")
    warnings: list[str] = []
    if isinstance(raw_suggestions, list):
        suggestions = [s for s in raw_suggestions if isinstance(s, dict)]
        if len(suggestions) != len(raw_suggestions):
            warnings.append("Non-object suggestions were ignored.")
    else:
        suggestions, read_warnings = _read_saved_target_suggestions(package_path)
        warnings.extend(read_warnings)

    selected_ids = body.get("target_ids")
    selected: set[str] | None = None
    if isinstance(selected_ids, list):
        selected = {str(x) for x in selected_ids if isinstance(x, (str, int))}

    normalized_suggestions = []
    for suggestion in suggestions:
        if selected is not None and str(suggestion.get("target_id")) not in selected:
            continue
        normalized_suggestions.append(_normalize_suggestion_for_design_target(suggestion))

    if not normalized_suggestions:
        return {
            "ok": False,
            "template_id": template_id,
            "project_id": project_id,
            "artifact_path": None,
            "adopted_count": 0,
            "skipped_duplicate_ids": [],
            "errors": [_error("no_suggestions", "No target suggestions are available to adopt.")],
            "warnings": warnings,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    existing_response = get_design_targets(settings, project_id)
    existing_targets = list(existing_response.get("targets") or [])
    existing_ids = {
        str(t.get("target_id") or t.get("id"))
        for t in existing_targets
        if isinstance(t, dict) and (t.get("target_id") or t.get("id"))
    }

    overwrite_existing = bool(body.get("overwrite_existing", False))
    skipped_duplicate_ids: list[str] = []
    adopted_targets: list[dict[str, Any]] = []
    if overwrite_existing:
        replacement_ids = {str(t.get("target_id")) for t in normalized_suggestions if t.get("target_id")}
        existing_targets = [
            t for t in existing_targets
            if not (isinstance(t, dict) and str(t.get("target_id") or t.get("id")) in replacement_ids)
        ]
    for target in normalized_suggestions:
        tid = str(target.get("target_id") or "")
        if not overwrite_existing and tid in existing_ids:
            skipped_duplicate_ids.append(tid)
            continue
        adopted_targets.append(target)

    if not adopted_targets:
        return {
            "ok": True,
            "template_id": template_id,
            "project_id": project_id,
            "artifact_path": existing_response.get("artifact_path"),
            "document": existing_response.get("document"),
            "targets": existing_targets,
            "adopted_count": 0,
            "skipped_duplicate_ids": skipped_duplicate_ids,
            "errors": [],
            "warnings": warnings + ["All selected suggestions already exist in task/design_targets.yaml."],
            "safety_note": ADOPTED_TARGETS_NOTE,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    existing_doc = existing_response.get("document")
    doc = dict(existing_doc) if isinstance(existing_doc, dict) else {"schema_version": "0.1"}
    doc["schema_version"] = str(doc.get("schema_version") or "0.1")
    doc["targets"] = existing_targets + adopted_targets
    metadata = dict(doc.get("metadata")) if isinstance(doc.get("metadata"), dict) else {}
    metadata["template_handoff"] = {
        "template_id": template_id,
        "adopted_count": len(adopted_targets),
        "adopted_at": _now_iso(),
        "claim_advancement": CLAIM_ADVANCEMENT,
        "note": ADOPTED_TARGETS_NOTE,
    }
    doc["metadata"] = metadata
    validation_errors = validate_design_targets_document(doc)
    if validation_errors:
        return {
            "ok": False,
            "template_id": template_id,
            "project_id": project_id,
            "artifact_path": None,
            "adopted_count": 0,
            "skipped_duplicate_ids": skipped_duplicate_ids,
            "errors": [
                _error("invalid_adopted_target", e.get("message", "Invalid target."), field=e.get("field"))
                for e in validation_errors
            ],
            "warnings": warnings,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    saved = save_design_targets(settings, project_id, doc)
    return {
        "ok": True,
        "template_id": template_id,
        "project_id": project_id,
        "artifact_path": saved.get("artifact_path"),
        "document": saved.get("document"),
        "targets": saved.get("targets", []),
        "adopted_count": len(adopted_targets),
        "skipped_duplicate_ids": skipped_duplicate_ids,
        "errors": [],
        "warnings": warnings,
        "safety_note": ADOPTED_TARGETS_NOTE,
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _read_saved_draft_parameters(package_path: Path, template_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Read parameters from a saved engineering setup draft, when present."""
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if DRAFT_MANIFEST_PATH not in zf.namelist():
                return None, [f"No saved engineering setup draft found at {DRAFT_MANIFEST_PATH}."]
            doc = json.loads(zf.read(DRAFT_MANIFEST_PATH).decode("utf-8", errors="replace"))
    except Exception as exc:
        return None, [f"Could not read saved engineering setup draft: {type(exc).__name__}: {exc}"]
    if not isinstance(doc, dict):
        return None, [f"{DRAFT_MANIFEST_PATH} is not a JSON object."]
    if doc.get("template_id") != template_id:
        return None, [
            f"Saved draft template_id {doc.get('template_id')!r} does not match requested template {template_id!r}."
        ]
    params = doc.get("parameters")
    if not isinstance(params, dict):
        return None, [f"{DRAFT_MANIFEST_PATH} does not contain a parameters object."]
    return params, []


def _template_geometry_fixture(template_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic geometry metadata for the controlled template.

    This is not a B-rep, STEP, STL, FCStd, or solver mesh. It is a safe fixture
    that downstream AIENG code can inspect/review before a future approved CAD
    backend materializes real geometry.
    """
    material = _MATERIALS[params["material"]]
    common = {
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "material": {"id": params["material"], **material},
        "coordinate_system": {
            "x": "length/loading axis",
            "y": "height/width axis depending on template",
            "z": "width/thickness axis depending on template",
        },
    }
    if template_id == "cantilever_beam":
        length = float(params["length_mm"])
        width = float(params["width_mm"])
        height = float(params["height_mm"])
        return {
            **common,
            "geometry_kind": "rectangular_cantilever_fixture",
            "primitive": "box",
            "dimensions": {
                "length_mm": length,
                "width_mm": width,
                "height_mm": height,
            },
            "bounding_box_mm": {
                "min": [0.0, -height / 2.0, -width / 2.0],
                "max": [length, height / 2.0, width / 2.0],
            },
            "named_regions": [
                {"id": "x_min_face", "role": "fixed_support", "description": "Root face at x=0."},
                {"id": "x_max_face", "role": "load_application", "description": "Tip face at x=length."},
            ],
        }
    if template_id == "plate_with_hole":
        length = float(params["length_mm"])
        width = float(params["width_mm"])
        thickness = float(params["thickness_mm"])
        hole = float(params["hole_diameter_mm"])
        return {
            **common,
            "geometry_kind": "plate_with_central_hole_fixture",
            "primitive": "box_minus_cylinder",
            "dimensions": {
                "length_mm": length,
                "width_mm": width,
                "thickness_mm": thickness,
                "hole_diameter_mm": hole,
            },
            "bounding_box_mm": {
                "min": [0.0, -width / 2.0, -thickness / 2.0],
                "max": [length, width / 2.0, thickness / 2.0],
            },
            "features": [
                {
                    "id": "central_hole",
                    "type": "through_hole",
                    "diameter_mm": hole,
                    "center_mm": [length / 2.0, 0.0, 0.0],
                }
            ],
            "named_regions": [
                {"id": "x_min_face", "role": "fixed_support", "description": "Clamped face at x=0."},
                {"id": "x_max_face", "role": "load_application", "description": "Tensile-load face at x=length."},
                {"id": "hole_wall", "role": "stress_concentration_review", "description": "Cylindrical hole wall."},
            ],
        }
    raise HTTPException(status_code=500, detail=f"unknown template {template_id}")


def _build_cad_fixture_document(
    template_id: str,
    project_id: str,
    params: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "template_cad_fixture",
        "template_id": template_id,
        "project_id": project_id,
        "generated_at": _now_iso(),
        "source": source,
        "source_draft_path": DRAFT_MANIFEST_PATH if source == "saved_draft" else None,
        "parameters": params,
        "geometry": _template_geometry_fixture(template_id, params),
        "cad_execution_performed": False,
        "external_tool_execution_performed": False,
        "real_cad_file": False,
        "requires_approval": True,
        "output_artifact": GENERATED_CAD_FIXTURE_PATH,
        "stale_artifacts_on_success": [
            p for p in _GEOMETRY_STALE_ARTIFACTS if p != GENERATED_CAD_FIXTURE_PATH
        ],
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
        "safety_note": CAD_FIXTURE_NOTE,
    }


def generate_template_cad_fixture(
    settings: Settings,
    project_id: str,
    template_id: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Approval-gated deterministic CAD fixture write for controlled templates.

    Writes ``geometry/template_cad_fixture.json`` plus the standard stale
    revalidation marker. It never executes CAD tools and never creates a real
    STEP/FCStd/B-rep model.
    """
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown template '{template_id}'")

    try:
        package_path = _resolve_package(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {
                "ok": False,
                "template_id": template_id,
                "project_id": project_id,
                "status": "error",
                "requires_approval": True,
                "cad_execution_performed": False,
                "external_tool_execution_performed": False,
                "errors": [_error("package_not_found", "Project has no .aieng package; cannot write CAD fixture.")],
                "warnings": [],
                "claim_advancement": CLAIM_ADVANCEMENT,
                "claim_boundary": CLAIM_BOUNDARY,
            }
        raise

    body = payload if isinstance(payload, dict) else {}
    approved = body.get("approved") is True or body.get("approval") is True
    if not approved:
        return {
            "ok": False,
            "template_id": template_id,
            "project_id": project_id,
            "status": "waiting_for_approval",
            "requires_approval": True,
            "cad_execution_performed": False,
            "external_tool_execution_performed": False,
            "artifact_path": GENERATED_CAD_FIXTURE_PATH,
            "stale_artifacts": [p for p in _GEOMETRY_STALE_ARTIFACTS if p != GENERATED_CAD_FIXTURE_PATH],
            "warnings": [
                "CAD fixture generation writes geometry metadata and marks downstream evidence stale; explicit approval is required."
            ],
            "errors": [],
            "safety_note": CAD_FIXTURE_NOTE,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    source = "request_parameters"
    raw_params = body.get("parameters") if isinstance(body.get("parameters"), dict) else None
    warnings: list[str] = []
    if raw_params is None:
        raw_params, warnings = _read_saved_draft_parameters(package_path, template_id)
        source = "saved_draft"
    normalized, errors, validation_warnings = _validate_parameters(template, raw_params)
    warnings.extend(validation_warnings)
    if errors:
        return {
            "ok": False,
            "template_id": template_id,
            "project_id": project_id,
            "status": "error",
            "requires_approval": True,
            "cad_execution_performed": False,
            "external_tool_execution_performed": False,
            "errors": errors,
            "warnings": warnings,
            "safety_note": CAD_FIXTURE_NOTE,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    fixture = _build_cad_fixture_document(template_id, project_id, normalized, source=source)
    tmp = Path(tempfile.gettempdir()) / f"template_cad_fixture_{project_id}.json"
    tmp.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        artifact = write_artifact_to_package(package_path, GENERATED_CAD_FIXTURE_PATH, tmp, overwrite=True)
    finally:
        if tmp.exists():
            tmp.unlink()

    stale_artifacts = list(fixture["stale_artifacts_on_success"])
    _record_geometry_edit_in_package(package_path, affected_artifacts=stale_artifacts)

    return {
        "ok": True,
        "template_id": template_id,
        "project_id": project_id,
        "status": "completed",
        "requires_approval": True,
        "artifact": artifact,
        "artifact_path": GENERATED_CAD_FIXTURE_PATH,
        "revalidation_status_path": REVALIDATION_STATUS_PATH,
        "fixture": fixture,
        "stale_artifacts": stale_artifacts,
        "cad_execution_performed": False,
        "external_tool_execution_performed": False,
        "real_cad_file": False,
        "warnings": warnings,
        "errors": [],
        "safety_note": CAD_FIXTURE_NOTE,
        "claim_advancement": CLAIM_ADVANCEMENT,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def read_engineering_setup_draft_summary(pkg_path: Path) -> dict[str, Any] | None:
    """Lightweight read of the manifest for Project Health / Review Packet display.

    Returns None when no draft has ever been saved into this package.
    """
    try:
        with zipfile.ZipFile(pkg_path, "r") as zf:
            if DRAFT_MANIFEST_PATH not in zf.namelist():
                return None
            data = json.loads(zf.read(DRAFT_MANIFEST_PATH).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "template_id": data.get("template_id"),
        "generated_at": data.get("generated_at"),
        "parameter_count": len(data.get("parameters") or {}),
        "manifest_path": DRAFT_MANIFEST_PATH,
        "artifact_paths": list((data.get("artifacts") or {}).values()),
    }


__all__ = [
    "CLAIM_ADVANCEMENT",
    "CLAIM_BOUNDARY",
    "DRAFT_CAD_SCRIPT_PATH",
    "DRAFT_FEA_SETUP_PATH",
    "DRAFT_MANIFEST_PATH",
    "DRAFT_TARGET_SUGGESTIONS_PATH",
    "GENERATED_CAD_FIXTURE_PATH",
    "TEMPLATE_IDS",
    "get_engineering_template",
    "adopt_template_target_suggestions",
    "generate_template_cad_fixture",
    "list_engineering_templates",
    "preview_template",
    "read_engineering_setup_draft_summary",
    "save_template_draft",
]
