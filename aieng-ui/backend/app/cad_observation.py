"""CAD Observation v1 (v0.36).

After an :mod:`intent_planner` action touches CAD-related package state
(today: ``engineering_template.generate_cad_fixture``; tomorrow: any
``cad.source.*`` action that writes geometry), the Pilot
Console consumer needs to know what the CAD state actually *is* — not
what the runtime *claimed* it wrote.

This module is a pure, read-only observer over the existing
``.aieng`` package. It never executes CAD and never trusts a single
file path to be the source of truth: evidence levels are derived from
the presence of explicit, recognised members.

Honesty rules (enforced by ``observe_cad_state``):

  * Metadata-only artifacts (``geometry/template_cad_fixture.json``,
    template manifests, design intent) never lift the evidence level
    above ``metadata``.
  * A descriptor like ``graph/feature_graph.json`` is *not* by itself
    proof of real geometry. We only report ``exported_geometry`` when
    an actual binary CAD member (``.step`` / ``.stp`` / ``.fcstd`` /
    ``.brep``) is present.
  * A live CAD snapshot file (``geometry/live_snapshot.json``) lifts
    the level to ``live_cad_snapshot``. v0.36 does not write that
    file; the schema just supports it so a future provider integration
    can plug in.
  * Mesh readiness, watertightness, solver readiness, and physical
    correctness are never claimed from metadata.

The observation is intentionally consumed by
:mod:`agent_observation` and attached to ``IntentObservation`` for
CAD-related actions only. Use :func:`is_cad_related_action` to gate
that integration; the helper is conservative — when in doubt, do not
attach a CAD observation.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Iterable, Literal

from . import package_inspection as _pi


from .honesty import CAD_OBSERVATION_CLAIM_BOUNDARY as CLAIM_BOUNDARY

SCHEMA_VERSION = "0.1"


# Public type aliases. Kept as ``Literal`` so the schema stays stable for
# downstream consumers (frontend types, future MCP bridges).
CadObservationStatus = Literal[
    "available",
    "metadata_only",
    "missing",
    "invalid",
    "unknown",
]
CadGeometryEvidenceLevel = Literal[
    "none",
    "metadata",
    "exported_geometry",
    "live_cad_snapshot",
]


# ── recognised package members ───────────────────────────────────────────────


# Binary CAD payloads — presence of any of these promotes evidence to
# ``exported_geometry``.
_BINARY_CAD_EXTENSIONS: tuple[str, ...] = (
    ".step",
    ".stp",
    ".fcstd",
    ".brep",
    ".iges",
    ".igs",
)

# Known descriptor members. Their presence alone is not enough to claim
# real geometry, but they enrich ``known_*`` outputs.
_DESCRIPTOR_PATHS: tuple[str, ...] = (
    "graph/feature_graph.json",
    "graph/aag.json",
    "geometry/topology_map.json",
    "objects/interface_graph.json",
    "objects/object_registry.json",
)

# Metadata-only artifacts produced by template authoring.
_TEMPLATE_FIXTURE_PATH = "geometry/template_cad_fixture.json"
_TEMPLATE_DRAFT_MANIFEST = "task/engineering_setup_draft.json"
_TEMPLATE_CAD_SCRIPT = "task/cad_template_preview.py"
_TEMPLATE_FEA_SETUP = "task/fea_setup_draft.json"
_TEMPLATE_TARGETS_SUGGESTIONS = "task/design_targets_suggestions.yaml"

# Design intent.
_DESIGN_TARGETS_PRIMARY = "task/design_targets.yaml"
_DESIGN_TARGETS_FALLBACK = "task/design_targets.yml"

# Forward-compatible live-snapshot path. The schema accepts the snapshot but
# v0.36 does not write it; a future provider integration may drop a
# ``live_snapshot.json`` here. ``geometry/live_snapshot.json`` keeps
# CAD-derived state under ``geometry/`` next to other CAD artifacts.
_LIVE_SNAPSHOT_PATH = "geometry/live_snapshot.json"

# The most-recent edit's diff, persisted by cad_generation._write_last_edit_diff
# on every CAD mutation. Must match cad_generation._LAST_EDIT_DIFF_MEMBER.
_LAST_EDIT_DIFF_PATH = "state/last_edit_diff.json"


def _summarize_last_edit_diff(payload: Any) -> dict[str, Any] | None:
    """Compact the persisted last-edit diff into an agent-context summary, or None.

    Surfaces the trust verdict of the most recent CAD mutation
    (``regression_diff`` topology drift + ``critique_diff`` manufacturability) so
    a connecting agent sees "the last edit was clean / introduced a collateral
    change / made a new manufacturability finding" in ``aieng.agent_context``
    without re-running anything. Pure and tolerant of partial payloads.

    ``needs_attention`` is true only for the genuinely-worse verdicts — a
    regression ``collateral_change`` or a critique ``fail`` / ``warn`` — not for
    an expected ``topology_changed`` (e.g. a part was removed).
    """
    if not isinstance(payload, dict):
        return None
    reg = payload.get("regression_diff") if isinstance(payload.get("regression_diff"), dict) else None
    crit = payload.get("critique_diff") if isinstance(payload.get("critique_diff"), dict) else None
    if reg is None and crit is None:
        return None
    reg_verdict = reg.get("verdict") if reg else None
    crit_verdict = crit.get("verdict") if crit else None
    collateral = [str(p) for p in (reg.get("collateral_parts") or [])] if reg else []
    try:
        introduced = int(crit.get("introduced_count") or 0) if crit else 0
    except (TypeError, ValueError):
        introduced = 0
    needs_attention = reg_verdict == "collateral_change" or crit_verdict in ("fail", "warn")
    return {
        "tool": payload.get("tool"),
        "regression_verdict": reg_verdict,
        "critique_verdict": crit_verdict,
        "collateral_parts": collateral,
        "introduced_finding_count": introduced,
        "needs_attention": needs_attention,
    }


# ── CAD-related action gate ──────────────────────────────────────────────────


_CAD_RELATED_TOOL_NAMES = frozenset({
    "engineering_template.generate_cad_fixture",
})


def is_cad_related_action(action: dict[str, Any] | None) -> bool:
    """Return ``True`` when the IntentAction merits a CAD observation.

    Accepts ``None`` defensively so callers can chain
    ``cad_observation.is_cad_related_action(intent_planner.find_action(...))``.

    Future ``cad.source.*`` tools are matched by prefix
    so new families do not require a code change here.
    """
    if not isinstance(action, dict):
        return False
    tool_name = str(action.get("tool_name") or "")
    if tool_name in _CAD_RELATED_TOOL_NAMES:
        return True
    if tool_name.startswith("cad.source."):
        return True
    # Allow callers to hint via the expected_artifacts field. Any
    # artifact under geometry/ or anything explicitly tagged as CAD
    # promotes the action to CAD-related.
    expected = action.get("expected_artifacts")
    if isinstance(expected, list):
        for artifact in expected:
            if not isinstance(artifact, str):
                continue
            if artifact.startswith("geometry/") or "cad" in artifact.lower():
                return True
    return False


# ── helpers ──────────────────────────────────────────────────────────────────


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _resolve_package_path(settings: Any, project_id: str | None) -> Path | None:
    if not project_id:
        return None
    # Imported lazily to avoid pulling FastAPI into a pure module.
    from .copilot_loop import _resolve_package
    from fastapi import HTTPException

    try:
        return _resolve_package(settings, str(project_id))
    except HTTPException:
        return None
    except Exception:
        return None


def _binary_cad_members(names: set[str]) -> list[str]:
    out: list[str] = []
    for name in sorted(names):
        lowered = name.lower()
        if any(lowered.endswith(ext) for ext in _BINARY_CAD_EXTENSIONS):
            out.append(name)
    return out


def _topology_count_summary(topology: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if isinstance(topology, dict):
        for key in ("faces", "edges", "vertices", "shells", "solids"):
            value = topology.get(key)
            if isinstance(value, list):
                counts[key] = len(value)
            elif isinstance(value, dict):
                counts[key] = len(value)
    return counts


def _feature_graph_summary(feature_graph: Any) -> dict[str, Any]:
    if not isinstance(feature_graph, dict):
        return {"feature_count": 0, "feature_ids": []}
    features = feature_graph.get("features")
    if not isinstance(features, list):
        return {"feature_count": 0, "feature_ids": []}
    ids: list[str] = []
    for feature in features:
        if isinstance(feature, dict):
            fid = feature.get("id") or feature.get("feature_id")
            if isinstance(fid, str):
                ids.append(fid)
    return {"feature_count": len(features), "feature_ids": ids[:25]}


def _collect_template_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    geometry = fixture.get("geometry") if isinstance(fixture.get("geometry"), dict) else {}
    return {
        "template_id": fixture.get("template_id"),
        "geometry_kind": geometry.get("geometry_kind"),
        "primitive": geometry.get("primitive"),
        "dimensions": geometry.get("dimensions") if isinstance(geometry.get("dimensions"), dict) else {},
        "named_regions": geometry.get("named_regions") if isinstance(geometry.get("named_regions"), list) else [],
        "features": geometry.get("features") if isinstance(geometry.get("features"), list) else [],
        "material": geometry.get("material") if isinstance(geometry.get("material"), dict) else {},
    }


# ── recommendations ──────────────────────────────────────────────────────────


def _rec(kind: str, label: str, rationale: str, **extra: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "kind": kind,
        "label": label,
        "rationale": rationale,
    }
    rec.update(extra)
    return rec


def cad_specific_recommendations(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """Heuristic CAD/CAE next-step recommender.

    The observation is the dictionary returned by :func:`observe_cad_state`.
    The recommender returns *advice*, not queued runs.
    """
    status = observation.get("status")
    evidence = observation.get("geometry_evidence_level")
    out: list[dict[str, Any]] = []

    # Self-correction: when the geometry report flags floating parts or broken
    # symmetry, point the agent at the read-only design review (which binds each
    # fixable finding to a concrete cad.edit_parameter target) before it presents
    # the result as done.
    floating = observation.get("floating_parts") or []
    broken_sym = observation.get("broken_symmetry") or []
    if floating or broken_sym:
        out.append(_rec(
            "run_design_review",
            "Run cad.design_review for a prioritized, fixable list of the geometry issues.",
            rationale=(
                f"The geometry report flags {len(floating)} floating part(s) and "
                f"{len(broken_sym)} broken-symmetry part(s). design_review binds each "
                "fixable finding to a concrete cad.edit_parameter target; fix the "
                "highest-severity ones, then re-run."
            ),
            reference="cad.design_review",
        ))

    if status == "missing" or evidence == "none":
        out.append(_rec(
            "generate_cad_fixture",
            "Generate a template CAD fixture or import real CAD geometry.",
            rationale=(
                "No CAD evidence exists in the package yet. AIENG cannot "
                "discuss readiness for mesh or solver without at least "
                "metadata-level CAD state."
            ),
            reference="engineering_template.generate_cad_fixture",
        ))
        return out

    if evidence == "metadata":
        out.append(_rec(
            "import_real_geometry",
            "Import or generate real CAD geometry (STEP/FCStd) for this template fixture.",
            rationale=(
                "Only metadata-level CAD evidence exists. CAE decisions taken "
                "from metadata alone are not evidence-backed."
            ),
            reference="cad.export_step",
        ))
        if not observation.get("semantic_labels"):
            out.append(_rec(
                "label_functional_regions",
                "Add semantic labels for functional regions (load surfaces, supports, joints).",
                rationale=(
                    "Without semantic labels, downstream CAE actions cannot tell which "
                    "regions carry loads or boundary conditions."
                ),
                reference="objects/object_registry",
            ))
        if not observation.get("known_load_candidates"):
            out.append(_rec(
                "identify_load_candidates",
                "Identify the regions where loads will be applied.",
                rationale=(
                    "Load candidates are unknown. CAE setup will be ambiguous "
                    "until at least one load region is named."
                ),
                reference="task/load_cases",
            ))
        if not observation.get("known_support_candidates"):
            out.append(_rec(
                "identify_support_candidates",
                "Identify the regions where boundary conditions will be applied.",
                rationale=(
                    "Boundary condition candidates are unknown. Solver setup "
                    "cannot proceed honestly without at least one support region."
                ),
                reference="task/boundary_conditions",
            ))

    if evidence in {"exported_geometry", "live_cad_snapshot"} and "simulation/mesh" not in (observation.get("cae_readiness_hints") or {}).get("present_paths", []):
        out.append(_rec(
            "inspect_geometry_readiness",
            "Inspect geometry readiness before approving mesh generation or solver setup.",
            rationale=(
                "Real geometry is present, but no mesh evidence was found. "
                "Confirm topology, units, and watertightness before approving "
                "downstream tools."
            ),
            reference="aieng.inspect_package",
        ))

    if not out:
        out.append(_rec(
            "review_cad_observation",
            "Review the CAD observation and decide the next manual step.",
            rationale=(
                "No deterministic CAD recommendation was derived from the "
                "current package state."
            ),
            reference="cad_observation",
        ))
    return out


# ── main entry ───────────────────────────────────────────────────────────────


def observe_cad_state(
    settings: Any,
    project_id: str | None,
    *,
    package_reader: _pi.PackageReadCache | None = None,
) -> dict[str, Any]:
    """Build a :class:`CADObservation` for the project's current CAD state.

    The function is pure and read-only. It never executes CAD tools and
    never mutates the package. If the package cannot be opened, the
    observation surfaces ``status=unknown`` so a UI knows not to claim
    anything about CAD state.
    """
    package_path = _resolve_package_path(settings, project_id)
    if package_path is None or not package_path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "missing" if project_id else "unknown",
            "source_artifacts": [],
            "geometry_evidence_level": "none",
            "summary": (
                "No .aieng package is available for this project; no CAD evidence."
                if project_id
                else "No project_id was supplied; CAD state cannot be observed."
            ),
            "known_geometry": {},
            "known_parameters": {},
            "known_materials": {},
            "known_load_candidates": [],
            "known_support_candidates": [],
            "known_named_regions": [],
            "semantic_labels": [],
            "topology_references": {},
            "missing_information": [
                "geometry/template_cad_fixture.json or real CAD source",
            ],
            "cae_readiness_hints": {
                "mesh_evidence": False,
                "solver_input_evidence": False,
                "computed_metrics_evidence": False,
                "present_paths": [],
            },
            "last_edit": None,
            "warnings": [
                "No package available; CAD readiness cannot be evaluated."
            ],
            "claim_advancement": "none",
            "claim_boundary": CLAIM_BOUNDARY,
        }

    owns_reader = package_reader is None
    try:
        zf = package_reader or _pi.PackageReadCache(package_path)
    except (zipfile.BadZipFile, OSError) as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "unknown",
            "source_artifacts": [str(package_path)],
            "geometry_evidence_level": "none",
            "summary": f"Could not read .aieng package: {type(exc).__name__}: {exc}",
            "known_geometry": {},
            "known_parameters": {},
            "known_materials": {},
            "known_load_candidates": [],
            "known_support_candidates": [],
            "known_named_regions": [],
            "semantic_labels": [],
            "topology_references": {},
            "missing_information": ["readable package"],
            "cae_readiness_hints": {
                "mesh_evidence": False,
                "solver_input_evidence": False,
                "computed_metrics_evidence": False,
                "present_paths": [],
            },
            "last_edit": None,
            "warnings": ["The package could not be opened; observation is incomplete."],
            "claim_advancement": "none",
            "claim_boundary": CLAIM_BOUNDARY,
        }

    try:
        names = set(zf.namelist())

        binary_cad = _binary_cad_members(names)
        has_live_snapshot = _LIVE_SNAPSHOT_PATH in names
        has_fixture = _TEMPLATE_FIXTURE_PATH in names
        has_template_draft = _TEMPLATE_DRAFT_MANIFEST in names
        has_design_targets = (
            _DESIGN_TARGETS_PRIMARY in names or _DESIGN_TARGETS_FALLBACK in names
        )

        descriptor_present = [path for path in _DESCRIPTOR_PATHS if path in names]

        fixture = _pi.read_package_json(zf, _TEMPLATE_FIXTURE_PATH) if has_fixture else None
        template_manifest = (
            _pi.read_package_json(zf, _TEMPLATE_DRAFT_MANIFEST)
            if has_template_draft else None
        )
        live_snapshot = (
            _pi.read_package_json(zf, _LIVE_SNAPSHOT_PATH) if has_live_snapshot else None
        )
        feature_graph = _pi.read_package_json(zf, "graph/feature_graph.json")
        topology = _pi.read_package_json(zf, "geometry/topology_map.json")
        last_edit = _summarize_last_edit_diff(
            _pi.read_package_json(zf, _LAST_EDIT_DIFF_PATH) if _LAST_EDIT_DIFF_PATH in names else None
        )

        # Evidence level. Order matters: live > exported > metadata > none.
        if has_live_snapshot:
            evidence_level: CadGeometryEvidenceLevel = "live_cad_snapshot"
        elif binary_cad:
            evidence_level = "exported_geometry"
        elif has_fixture or has_template_draft or descriptor_present:
            evidence_level = "metadata"
        else:
            evidence_level = "none"

        # Status. ``invalid`` is reserved for cases where a CAD artifact
        # exists but its content is unreadable / structurally wrong.
        invalid_artifacts: list[str] = []
        if has_fixture and not isinstance(fixture, dict):
            invalid_artifacts.append(_TEMPLATE_FIXTURE_PATH)
        if has_live_snapshot and not isinstance(live_snapshot, dict):
            invalid_artifacts.append(_LIVE_SNAPSHOT_PATH)

        if invalid_artifacts:
            status: CadObservationStatus = "invalid"
        elif evidence_level in {"exported_geometry", "live_cad_snapshot"}:
            status = "available"
        elif evidence_level == "metadata":
            status = "metadata_only"
        else:
            status = "missing"

        source_artifacts: list[str] = []
        if has_live_snapshot:
            source_artifacts.append(_LIVE_SNAPSHOT_PATH)
        source_artifacts.extend(binary_cad)
        if has_fixture:
            source_artifacts.append(_TEMPLATE_FIXTURE_PATH)
        if has_template_draft:
            source_artifacts.append(_TEMPLATE_DRAFT_MANIFEST)
        source_artifacts.extend(descriptor_present)

        # Known geometry / parameters / materials / regions. Prefer
        # live-snapshot data when present (forward-compatible path); fall
        # back to fixture metadata.
        known_geometry: dict[str, Any] = {}
        known_parameters: dict[str, Any] = {}
        known_materials: dict[str, Any] = {}
        named_regions: list[dict[str, Any]] = []
        load_candidates: list[dict[str, Any]] = []
        support_candidates: list[dict[str, Any]] = []
        semantic_labels: list[str] = []

        if isinstance(live_snapshot, dict):
            ls_geometry = live_snapshot.get("geometry")
            if isinstance(ls_geometry, dict):
                known_geometry.update({
                    "geometry_kind": ls_geometry.get("geometry_kind"),
                    "primitive": ls_geometry.get("primitive"),
                    "dimensions": ls_geometry.get("dimensions") if isinstance(ls_geometry.get("dimensions"), dict) else {},
                    "bounding_box_mm": ls_geometry.get("bounding_box_mm"),
                })
                regions = ls_geometry.get("named_regions")
                if isinstance(regions, list):
                    named_regions = [r for r in regions if isinstance(r, dict)]
            # Top-level named_regions are also honoured. Some provider
            # snapshot schemas put them at the top level; the template
            # fixture nests them under geometry. Accept both.
            top_regions = live_snapshot.get("named_regions")
            if isinstance(top_regions, list):
                named_regions.extend(r for r in top_regions if isinstance(r, dict))
            # Object-level semantic labels and material flow through too.
            objects = live_snapshot.get("objects")
            if isinstance(objects, list):
                for obj in objects:
                    if not isinstance(obj, dict):
                        continue
                    if not known_materials and isinstance(obj.get("material"), dict):
                        known_materials.update(obj["material"])
                    obj_labels = obj.get("semantic_labels")
                    if isinstance(obj_labels, list):
                        semantic_labels.extend(str(v) for v in obj_labels if v)
            ls_params = live_snapshot.get("parameters")
            if isinstance(ls_params, dict):
                known_parameters.update(ls_params)
            ls_material = live_snapshot.get("material")
            if isinstance(ls_material, dict):
                known_materials.update(ls_material)
            # Top-level topology_references propagate too.
            ls_topology = live_snapshot.get("topology_references")
            if isinstance(ls_topology, dict):
                # We'll merge into topology_references later (after the
                # feature_graph / topology_map fallbacks have been computed).
                pass
            for label_field in ("semantic_labels", "labels"):
                values = live_snapshot.get(label_field)
                if isinstance(values, list):
                    semantic_labels.extend(str(v) for v in values if v)
        elif isinstance(fixture, dict):
            collected = _collect_template_fixture(fixture)
            known_geometry.update({
                k: v for k, v in collected.items()
                if k in {"geometry_kind", "primitive", "dimensions"}
            })
            named_regions = list(collected["named_regions"])
            known_materials.update(collected["material"])
            params = fixture.get("parameters")
            if isinstance(params, dict):
                known_parameters.update(params)

        if isinstance(template_manifest, dict):
            params = template_manifest.get("parameters")
            if isinstance(params, dict):
                # Only fill in parameters we don't already know — live or fixture wins.
                for k, v in params.items():
                    known_parameters.setdefault(k, v)

        # Derive load / support candidates from named regions when the role
        # field follows the template convention.
        for region in named_regions:
            role = str(region.get("role") or "").lower()
            if "load" in role or "force" in role or "tension" in role:
                load_candidates.append(region)
            if "fix" in role or "support" in role or "clamp" in role:
                support_candidates.append(region)
            label = region.get("id") or region.get("name")
            if isinstance(label, str):
                semantic_labels.append(label)

        topology_references = _topology_count_summary(topology)
        topology_references.update(_feature_graph_summary(feature_graph))
        if isinstance(live_snapshot, dict):
            ls_topology = live_snapshot.get("topology_references")
            if isinstance(ls_topology, dict):
                for key, value in ls_topology.items():
                    topology_references.setdefault(str(key), value)

        # CAE readiness hints — these are surface-level signals only.
        mesh_evidence = any(name.startswith("simulation/mesh") for name in names)
        solver_input_evidence = any(
            name.endswith(".inp") or name == "simulation/solver_settings.json"
            for name in names
        )
        computed_metrics_evidence = "results/computed_metrics.json" in names
        present_paths: list[str] = []
        for prefix in ("simulation/mesh", "simulation/runs", "results"):
            if any(name.startswith(prefix) for name in names):
                present_paths.append(prefix)
        cae_readiness_hints = {
            "mesh_evidence": mesh_evidence,
            "solver_input_evidence": solver_input_evidence,
            "computed_metrics_evidence": computed_metrics_evidence,
            "present_paths": present_paths,
            "has_design_targets": has_design_targets,
        }

        # Missing information. Always honest about the difference between
        # ``no real geometry yet`` and ``not enough engineering context``.
        missing_information: list[str] = []
        if evidence_level == "none":
            missing_information.extend([
                "geometry/template_cad_fixture.json or imported CAD source",
                "topology",
                "feature_graph",
                "named_regions",
                "material",
                "load_candidates",
                "support_candidates",
            ])
        elif evidence_level == "metadata":
            if not binary_cad and not has_live_snapshot:
                missing_information.append("real geometry (STEP/FCStd) or live CAD snapshot")
            if not load_candidates:
                missing_information.append("explicit load_candidates")
            if not support_candidates:
                missing_information.append("explicit support_candidates")
            if not topology_references.get("faces") and not topology_references.get("feature_count"):
                missing_information.append("topology or feature_graph evidence")
        # exported_geometry / live_cad_snapshot: still surface anything not yet known.
        if evidence_level in {"exported_geometry", "live_cad_snapshot"}:
            if not topology_references.get("feature_count"):
                missing_information.append("feature_graph evidence")
            if not topology_references.get("faces"):
                missing_information.append("topology face data")
            if not load_candidates:
                missing_information.append("explicit load_candidates")
            if not support_candidates:
                missing_information.append("explicit support_candidates")

        warnings: list[str] = []
        if evidence_level == "metadata":
            warnings.append(
                "CAD fixture metadata exists, but no real CAD geometry evidence is "
                "available. This cannot prove the geometry is valid, watertight, "
                "meshable, or simulation-ready."
            )
        if status == "invalid":
            warnings.append(
                "One or more CAD artifacts could not be parsed; treat the package as untrusted."
            )
        if status == "missing":
            warnings.append("No CAD-related artifacts were found in this package.")
        if last_edit and last_edit.get("needs_attention"):
            bits: list[str] = []
            if last_edit.get("regression_verdict") == "collateral_change":
                bits.append(f"unintended parts changed ({', '.join(last_edit.get('collateral_parts') or []) or '?'})")
            if last_edit.get("critique_verdict") in ("fail", "warn"):
                bits.append(f"{last_edit.get('introduced_finding_count', 0)} new manufacturability finding(s)")
            warnings.append(
                "The last CAD edit's diff flagged a regression: "
                + "; ".join(bits)
                + ". Review `last_edit` before trusting the geometry."
            )

        summary_lines = [
            f"CAD state: {status}.",
            f"Geometry evidence level: {evidence_level}.",
        ]
        if binary_cad:
            summary_lines.append(f"Binary CAD members present: {', '.join(binary_cad[:3])}.")
        if has_fixture:
            summary_lines.append("Template CAD fixture metadata is present.")
        if has_live_snapshot:
            summary_lines.append("A live CAD snapshot artifact is present.")
        if missing_information:
            summary_lines.append(
                f"{len(missing_information)} missing-information items recorded."
            )
        summary = " ".join(summary_lines)

        # Geometry self-correction signals — the same structural data
        # cad.design_review folds in (floating parts, broken left/right
        # symmetry), surfaced here so a connected agent sees them without a
        # separate call. Computed from the topology map; best-effort.
        geometry_report_summary: str | None = None
        floating_parts: list[str] = []
        broken_symmetry: list[str] = []
        if isinstance(topology, dict) and topology.get("entities"):
            try:
                from .cad_generation import _compute_geometry_report, _geometry_report_summary

                report = _compute_geometry_report(topology)
                geometry_report_summary = _geometry_report_summary(report)
                floating_parts = [str(p) for p in (report.get("floating_parts") or [])]
                for sym in report.get("symmetry") or []:
                    if not isinstance(sym, dict):
                        continue
                    if sym.get("ok") is False or sym.get("status") == "missing_partner":
                        if sym.get("part"):
                            broken_symmetry.append(str(sym["part"]))
                        for name in sym.get("pair") or []:
                            if name:
                                broken_symmetry.append(str(name))
            except Exception:
                geometry_report_summary = None
        broken_symmetry = _unique(broken_symmetry)

        observation = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "source_artifacts": _unique(source_artifacts),
            "geometry_evidence_level": evidence_level,
            "summary": summary,
            "geometry_report_summary": geometry_report_summary,
            "floating_parts": floating_parts,
            "broken_symmetry": broken_symmetry,
            "known_geometry": known_geometry,
            "known_parameters": known_parameters,
            "known_materials": known_materials,
            "known_load_candidates": load_candidates,
            "known_support_candidates": support_candidates,
            "known_named_regions": named_regions,
            "semantic_labels": _unique(semantic_labels),
            "topology_references": topology_references,
            "missing_information": _unique(missing_information),
            "cae_readiness_hints": cae_readiness_hints,
            "last_edit": last_edit,
            "warnings": warnings,
            "claim_advancement": "none",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        observation["next_recommended_actions"] = cad_specific_recommendations(observation)
        return observation
    finally:
        if owns_reader:
            zf.close()


__all__ = [
    "CLAIM_BOUNDARY",
    "CadGeometryEvidenceLevel",
    "CadObservationStatus",
    "SCHEMA_VERSION",
    "cad_specific_recommendations",
    "is_cad_related_action",
    "observe_cad_state",
]
