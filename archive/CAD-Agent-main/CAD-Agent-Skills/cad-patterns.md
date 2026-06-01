# CadQuery CAD Compiler Script Patterns

Use these helpers when generating CadQuery scripts for adaptive iterations, validation, review reports, and feature memory.

## Iteration script scope header

Every `scripts/iteration_<nn>_<intent>.py` must open with a short scope block (module docstring is ideal) so the **agent self-review** (or a human) can verify the iteration did not accidentally become a full-model dump. Align with [SKILL.md](SKILL.md) *Single-focus iteration discipline* and [pipeline-contract.md](pipeline-contract.md).

Example:

```text
"""
iteration_02_hull_loft — primary scope: loft main hull from station profiles A–D only.
In scope: station profiles A-D, one lofted hull body, hull bbox/volume refs.
Out of scope for this iteration: shell, windows, landing gear, fillets, second hull segment.
Deferred features: shell, windows, landing gear, panel seams, final chamfers.
Scope guard: this file must not produce a complete vehicle/ship/object model.
"""
```

## Base Skeleton

```python
from pathlib import Path
import json

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exports"
PIPELINE = OUT / "pipeline"
OUT.mkdir(parents=True, exist_ok=True)
PIPELINE.mkdir(parents=True, exist_ok=True)

feature_memory = []

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def add_memory(entry):
    feature_memory.append(entry)
    write_json(PIPELINE / "feature_memory.json", feature_memory)

def primary_shape(result):
    if hasattr(result, "val"):
        return result.val()
    return result

def shape_bbox(shape):
    bbox = shape.BoundingBox()
    return [bbox.xmin, bbox.xmax, bbox.ymin, bbox.ymax, bbox.zmin, bbox.zmax]

def validate_result(result, feature_name, expected_bbox=None, min_volume=0.0):
    shape = primary_shape(result)
    if shape is None:
        raise RuntimeError(f"{feature_name}: missing shape")
    if hasattr(shape, "isValid") and not shape.isValid():
        raise RuntimeError(f"{feature_name}: invalid shape")
    volume = shape.Volume() if hasattr(shape, "Volume") else 0.0
    if volume <= min_volume:
        raise RuntimeError(f"{feature_name}: invalid volume {volume}")
    bbox = shape_bbox(shape)
    if expected_bbox:
        xmin, xmax, ymin, ymax, zmin, zmax = expected_bbox
        if not (xmin <= bbox[0] and bbox[1] <= xmax and ymin <= bbox[2] and bbox[3] <= ymax and zmin <= bbox[4] and bbox[5] <= zmax):
            raise RuntimeError(f"{feature_name}: bounding box out of range")
    return {"volume": volume, "bbox": bbox}

def shape_counts(shape):
    counts = {}
    for name, getter in [
        ("solid_count", getattr(shape, "Solids", None)),
        ("face_count", getattr(shape, "Faces", None)),
        ("edge_count", getattr(shape, "Edges", None)),
        ("shell_count", getattr(shape, "Shells", None)),
    ]:
        try:
            counts[name] = len(getter()) if getter else None
        except Exception:
            counts[name] = None
    return counts

def write_geometry_facts(stage_name, result, quality_level, source_file, exports, detected_features=None, checks=None, geometry_quality_metrics=None):
    shape = primary_shape(result)
    bbox = shape_bbox(shape)
    dims = [bbox[1] - bbox[0], bbox[3] - bbox[2], bbox[5] - bbox[4]]
    facts = {
        "iteration": stage_name,
        "quality_level": quality_level,
        "source_file": source_file,
        "exports": exports,
        "geometry": {
            "bbox": bbox,
            "dimensions": dims,
            "volume": shape.Volume() if hasattr(shape, "Volume") else None,
            "valid": shape.isValid() if hasattr(shape, "isValid") else None,
            **shape_counts(shape),
        },
        "detected_features": detected_features or [],
        "geometry_quality_metrics": geometry_quality_metrics or {},
        "checks": checks or {},
    }
    path = PIPELINE / stage_name / "geometry_facts.json"
    write_json(path, facts)
    return path, facts

def write_cad_refs(stage_name, refs):
    path = PIPELINE / stage_name / "cad_refs.json"
    write_json(path, {"iteration": stage_name, "refs": refs})
    return path

def compare_expected_bbox(actual_bbox, expected_bbox, tolerance=0.5):
    labels = ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"]
    deltas = {label: actual_bbox[i] - expected_bbox[i] for i, label in enumerate(labels)}
    passed = all(abs(delta) <= tolerance for delta in deltas.values())
    return {"passed": passed, "deltas": deltas, "tolerance": tolerance}

def compare_feature_presence(feature_tree, cad_refs):
    planned = {item["feature"] for item in feature_tree if "feature" in item}
    present = set(cad_refs.keys())
    return {
        "planned_count": len(planned),
        "present_count": len(planned & present),
        "missing": sorted(planned - present),
        "extra_refs": sorted(present - planned),
    }

def record_primitive_usage(features):
    counts = {
        "box": 0,
        "cylinder": 0,
        "sphere": 0,
        "simple_prism": 0,
        "loft": 0,
        "sweep": 0,
        "revolve": 0,
        "spline_profile": 0,
    }
    for feature in features:
        for key in counts:
            counts[key] += int(feature.get("primitive_usage", {}).get(key, 0))
    return counts

def classify_primitive_stack_risk(primitive_usage, primary_surface_strategy, profile_driven_surface_coverage):
    primitive_total = sum(primitive_usage.get(key, 0) for key in ["box", "cylinder", "sphere", "simple_prism"])
    surface_total = sum(primitive_usage.get(key, 0) for key in ["loft", "sweep", "revolve", "spline_profile"])
    if primary_surface_strategy == "primitive_stack" and primitive_total > surface_total:
        return "high"
    if primitive_total >= max(6, surface_total * 2) and profile_driven_surface_coverage < 0.5:
        return "high"
    if profile_driven_surface_coverage < 0.35 and primitive_total >= surface_total:
        return "medium"
    return "low"

def build_geometry_quality_metrics(features, primary_surface_strategy, profile_driven_surface_coverage, edge_break_coverage):
    primitive_usage = record_primitive_usage(features)
    return {
        "primitive_usage": primitive_usage,
        "primary_surface_strategy": primary_surface_strategy,
        "primitive_stack_risk": classify_primitive_stack_risk(
            primitive_usage,
            primary_surface_strategy,
            profile_driven_surface_coverage,
        ),
        "profile_driven_surface_coverage": profile_driven_surface_coverage,
        "edge_break_coverage": edge_break_coverage,
    }

def feature_transaction(feature_name, build_fn, validate_fn):
    try:
        result = build_fn()
        validation = validate_fn(result)
        return result, validation
    except Exception as exc:
        raise RuntimeError(f"{feature_name} failed: {exc}") from exc
```

## Iteration Exports

For complex models, save iteration outputs so refinement does not overwrite useful progress. The `stage_name` parameter below is an iteration id such as `iteration_02_surface_refine`.

```python
def save_stage(stage_name, result, export_stl=False):
    stage_dir = PIPELINE / stage_name
    stage_dir.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(result, str(stage_dir / f"{stage_name}.step"))
    if export_stl:
        cq.exporters.export(result, str(stage_dir / f"{stage_name}.stl"))
    return stage_dir

def write_review_packet(stage_name, quality_level, export_ready, fail_first_objections, evidence_summary, next_actions, generated_files):
    review = [
        f"# {stage_name} Review Packet",
        "",
        "## State",
        f"- quality_state: {quality_level}",
        f"- export_ready: {export_ready}",
        "",
        "## Fail-First Objections",
        *[f"- {item}" for item in fail_first_objections],
        "",
        "## Evidence Summary",
        *[f"- {key}: {value}" for key, value in evidence_summary.items()],
        "",
        "## Required Next Actions",
        *[f"{idx + 1}. {item}" for idx, item in enumerate(next_actions)],
        "",
        "## Generated Files",
        *[f"- {item}" for item in generated_files],
        "",
    ]
    path = PIPELINE / stage_name / "review_packet.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(review), encoding="utf-8")
    return path

def record_repair_action(stage_name, failed_check, source_file, source_feature, action):
    path = PIPELINE / stage_name / "repair_actions.json"
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.append({
        "failed_check": failed_check,
        "source_file": source_file,
        "source_feature": source_feature,
        "action": action,
    })
    write_json(path, existing)
    return path

def write_render_unavailable(stage_name, attempted_renderer, reason, fallback_mode="manual_html_file_input", attempted_command=None):
    path = PIPELINE / stage_name / "render_unavailable.json"
    write_json(path, {
        "iteration": stage_name,
        "visual_review_unavailable": True,
        "attempted_renderer": attempted_renderer,
        "attempted_command": attempted_command,
        "reason": reason,
        "fallback_mode": fallback_mode,
    })
    return path

def write_visual_review_html(stage_name, replacements):
    template_path = ROOT / ".cursor" / "skills" / "cadquery-modeling" / "visual-review-template.html"
    html = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", str(value))
    path = PIPELINE / stage_name / "visual_review.html"
    path.write_text(html, encoding="utf-8")
    assert_visual_review_html(stage_name)
    return path

def assert_visual_review_html(stage_name):
    path = PIPELINE / stage_name / "visual_review.html"
    html = path.read_text(encoding="utf-8")
    required = [
        'data-template="cadquery-visual-review-v1"',
        "Interactive Three.js Viewer",
        "Visual Defect Audit",
        "three.module.js",
        "STLLoader",
        "./render_views/front.png",
        "./render_views/side.png",
        "./render_views/top.png",
        "./render_views/iso.png",
    ]
    missing = [marker for marker in required if marker not in html]
    if missing:
        raise RuntimeError(f"{stage_name}: visual_review.html is not template-compliant; missing {missing}")
    return True
```

## Screenshot Rendering Pattern

Use this helper after `save_stage(..., export_stl=True)`. It follows the preferred Python offscreen renderer path from [rendering.md](rendering.md).

```python
def render_stage_views_pyvista(stage_name, stl_path=None):
    try:
        import pyvista as pv
    except ImportError as exc:
        write_render_unavailable(
            stage_name,
            "pyvista/vtk",
            f"missing dependency: {exc}",
            attempted_command='python -c "import pyvista, vtk"',
        )
        return []

    stage_dir = PIPELINE / stage_name
    stl = Path(stl_path) if stl_path else stage_dir / f"{stage_name}.stl"
    if not stl.exists():
        write_render_unavailable(
            stage_name,
            "pyvista/vtk",
            f"missing STL: {stl}",
            attempted_command=f"pv.read({stl})",
        )
        return []

    render_dir = stage_dir / "render_views"
    render_dir.mkdir(parents=True, exist_ok=True)

    try:
        mesh = pv.read(str(stl))
        center = mesh.center
        distance = max(float(mesh.length), 1.0) * 2.2
        cx, cy, cz = center
        cameras = {
            "front": ((cx, cy - distance, cz), center, (0, 0, 1)),
            "side": ((cx + distance, cy, cz), center, (0, 0, 1)),
            "top": ((cx, cy, cz + distance), center, (0, 1, 0)),
            "iso": ((cx + distance * 0.8, cy - distance * 0.8, cz + distance * 0.6), center, (0, 0, 1)),
        }
        written = []
        for name, camera in cameras.items():
            plotter = pv.Plotter(off_screen=True, window_size=(1280, 960))
            plotter.set_background("white")
            plotter.add_mesh(mesh, color="#9cc9ff", smooth_shading=True, show_edges=False)
            plotter.camera_position = camera
            plotter.camera.zoom(1.1)
            path = render_dir / f"{name}.png"
            plotter.screenshot(str(path))
            plotter.close()
            written.append(str(path))
        return written
    except Exception as exc:
        write_render_unavailable(
            stage_name,
            "pyvista/vtk",
            f"render failed: {exc}",
            attempted_command=f"pv.read({stl}) + Plotter(off_screen=True).screenshot(...)",
        )
        return []
```

Do not treat `visual_review.html` as proof that screenshots exist. The iteration must either write the PNG files above or write `render_unavailable.json`.

Adaptive action states:

- `brainstorm`: requirements, strategy, or geometry is still ambiguous.
- `prototype`: first testable form or subsystem.
- `repair`: invalid geometry, failed booleans, missing refs, or broken exports.
- `proportion_refine`: silhouette, scale, landmarks, or massing.
- `surface_refine`: lofts, sweeps, guide curves, transitions, or shell strategy.
- `detail_add`: panels, seams, vents, bosses, ribs, fasteners, and interfaces.
- `simplify`: replace fragile geometry with a more stable strategy.
- `export_ready`: final validation, material metadata, and requested exports.

## Artifact Writers

Use these files as the persistent contract between iterations:

```python
write_json(PIPELINE / "feature_tree.json", feature_tree)
write_json(PIPELINE / "iteration_plan.json", iteration_plan)
write_json(PIPELINE / "reference_sources.json", reference_sources)
write_json(PIPELINE / "object_agnostic_checklist.json", object_agnostic_checklist)
write_json(PIPELINE / "reference_visual_checklist.json", reference_visual_checklist)
write_json(PIPELINE / "surface_plan.json", surface_plan)
(PIPELINE / "design_brief.md").write_text(design_brief_markdown, encoding="utf-8")
(PIPELINE / "decision_log.md").write_text(decision_log_markdown, encoding="utf-8")
```

Every later iteration must read or preserve these artifacts instead of reinterpreting the original prompt from scratch.

## Phase Gate Writers

Use these before and after each iteration script. `phase_gate.json` and `preflight_review.md` must exist before source modeling starts; `review_packet.json`/`.md` must exist before the next iteration or `export_ready`.

```python
def write_phase_gate(stage_name, phase_goal, in_scope, out_of_scope, tests, remaining_gap, exit_criteria):
    path = PIPELINE / stage_name / "phase_gate.json"
    write_json(path, {
        "iteration": stage_name,
        "phase_goal": phase_goal,
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "acceptance_tests": tests.get("acceptance_tests", []),
        "reference_tests": tests.get("reference_tests", []),
        "geometry_tests": tests.get("geometry_tests", []),
        "visual_tests": tests.get("visual_tests", []),
        "functional_tests": tests.get("functional_tests", []),
        "regression_tests": tests.get("regression_tests", []),
        "remaining_gap": remaining_gap,
        "exit_criteria": exit_criteria,
    })
    return path

def write_preflight_review(stage_name, measurable, convergence_reason, unresolved_unknowns):
    path = PIPELINE / stage_name / "preflight_review.md"
    lines = [
        f"# {stage_name} Preflight Review",
        "",
        "## Measurability",
        f"- measurable: {measurable}",
        "",
        "## Convergence",
        f"- {convergence_reason}",
        "",
        "## Unresolved Required / Unknown Dimensions",
        *[f"- {item}" for item in unresolved_unknowns],
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

def write_review_packet_json(stage_name, phase_gate_results, fail_first_objections=None, visual_defect_audit=None, reference_fidelity_audit=None, functional_audit=None, signature_feature_evidence=None, primitive_strategy_evidence=None, required_next_actions=None, final_challenge=None, quality_state="repair", export_ready=False):
    unresolved = [
        item for item in phase_gate_results
        if item.get("blocking_before_next_phase") and item.get("status") in {"fail", "partial", "unknown", "not_inspected"}
    ]
    path = PIPELINE / stage_name / "review_packet.json"
    write_json(path, {
        "iteration": stage_name,
        "quality_state": quality_state,
        "fail_first_objections": fail_first_objections or [],
        "phase_gate_results": phase_gate_results,
        "visual_defect_audit": visual_defect_audit or {},
        "reference_fidelity_audit": reference_fidelity_audit or {},
        "functional_audit": functional_audit or {},
        "signature_feature_evidence": signature_feature_evidence or [],
        "primitive_strategy_evidence": primitive_strategy_evidence or {},
        "unresolved_required_tests": unresolved,
        "required_next_actions": required_next_actions or [],
        "final_challenge": final_challenge or {},
        "export_ready": export_ready and not unresolved,
    })
    return path
```

Phase gate result entries inside `review_packet.json` must include `test_id`, `status`, `evidence`, `source_feature`, `repair_action`, and `remaining_gap`. A prose review cannot substitute for this JSON.

## Export Blocker Helpers

Use these helpers before writing an `export_ready` review packet.

```python
def classify_reference_state(reference_sources):
    return reference_sources.get("reference_state", "reference_limited")

def assert_no_export_ready_blockers(review_packet, reference_sources, object_agnostic_checklist, geometry_facts):
    blockers = []
    for item in review_packet.get("phase_gate_results", []):
        if item.get("blocking_before_export_ready") and item.get("status") in {"fail", "partial", "unknown", "not_inspected"}:
            blockers.append({"kind": "gate_result", "test_id": item.get("test_id"), "status": item.get("status")})
    for item in review_packet.get("fail_first_objections", []):
        if not isinstance(item, dict) or item.get("status") in {None, "fail", "partial", "unknown", "not_inspected"}:
            blockers.append({"kind": "fail_first_objection", "detail": item})

    reference_state = classify_reference_state(reference_sources)
    if reference_state in {"reference_limited", "inferred_only"}:
        blockers.append({"kind": "reference_state", "status": reference_state})

    unresolved_dimensions = object_agnostic_checklist.get("export_ready_blockers", [])
    blockers.extend({"kind": "object_agnostic_dimension", "detail": item} for item in unresolved_dimensions)

    metrics = geometry_facts.get("geometry_quality_metrics", {})
    if metrics.get("primitive_stack_risk") == "high":
        blockers.append({"kind": "primitive_stack_risk", "status": "high"})
    if metrics.get("primitive_stack_risk") == "medium" and not review_packet.get("signature_feature_evidence"):
        blockers.append({"kind": "primitive_signature_evidence_missing", "status": "medium"})

    if blockers:
        raise RuntimeError(f"export_ready blocked: {blockers}")
    return True

def compare_reference_ratios(actual, expected, tolerance):
    return {
        "actual": actual,
        "expected": expected,
        "tolerance": tolerance,
        "delta": actual - expected,
        "status": "pass" if abs(actual - expected) <= tolerance else "fail",
    }

def compare_required_features(required_features, cad_refs):
    missing = [feature for feature in required_features if feature not in cad_refs]
    return {
        "required_count": len(required_features),
        "present_count": len(required_features) - len(missing),
        "missing": missing,
        "status": "pass" if not missing else "fail",
    }

def write_convergence_report(stage_name, phase_goal, reduced_gap, remaining_gap):
    path = PIPELINE / stage_name / "convergence_report.json"
    write_json(path, {
        "iteration": stage_name,
        "phase_goal": phase_goal,
        "reduced_gap": reduced_gap,
        "remaining_gap": remaining_gap,
        "status": "pass" if reduced_gap else "fail",
    })
    return path
```

## Geometry Brain Writers

After saving an iteration, write evidence files:

```python
stage_dir = save_stage("iteration_02_surface_refine", model, export_stl=True)
rendered_views = render_stage_views_pyvista("iteration_02_surface_refine")

facts_path, facts = write_geometry_facts(
    "iteration_02_surface_refine",
    model,
    "surface_refine",
    "scripts/iteration_02_surface_refine.py",
    {
        "step": str(stage_dir / "iteration_02_surface_refine.step"),
        "stl": str(stage_dir / "iteration_02_surface_refine.stl"),
    },
    detected_features=[
        {
            "ref": "body.main_shell",
            "type": "primary_body",
            "intent": "main visible exterior shell",
            "primitive_usage": {"loft": 1, "spline_profile": 4},
            "bbox": validate_result(model, "SurfaceEnvelope")["bbox"],
        }
    ],
    geometry_quality_metrics=build_geometry_quality_metrics(
        features=[
            {"primitive_usage": {"loft": 1, "spline_profile": 4}},
        ],
        primary_surface_strategy="lofted_surface",
        profile_driven_surface_coverage=0.8,
        edge_break_coverage=0.4,
    ),
)

refs_path = write_cad_refs("iteration_02_surface_refine", {
    "body.main_shell": {
        "kind": "solid",
        "intent": "primary exterior housing",
        "source_feature": "SurfaceEnvelope",
        "source_file": "scripts/iteration_02_surface_refine.py",
        "bbox": facts["geometry"]["bbox"],
    }
})

html_path = write_visual_review_html("iteration_02_surface_refine", {
    "STAGE_NAME": "iteration_02_surface_refine",
    "QUALITY_LEVEL": "surface_refine",
    "SOURCE_FILE": "scripts/iteration_02_surface_refine.py",
    "GENERATED_AT": "replace with timestamp",
    "SUMMARY": "Evidence-based visual review for iteration_02_surface_refine.",
    "SILHOUETTE_STATUS_CLASS": "status-warn",
    "SILHOUETTE_STATUS": "needs review",
    "SILHOUETTE_EVIDENCE": "See front/side/top/iso views.",
    "SILHOUETTE_REPAIR": "Map failures to source features.",
    "PROPORTION_STATUS_CLASS": "status-warn",
    "PROPORTION_STATUS": "needs review",
    "PROPORTION_EVIDENCE": "Compare against geometry_facts dimensions.",
    "PROPORTION_REPAIR": "Adjust parameters or section stations.",
    "SURFACE_STATUS_CLASS": "status-warn",
    "SURFACE_STATUS": "needs review",
    "SURFACE_EVIDENCE": "Check wire/iso views.",
    "SURFACE_REPAIR": "Revise loft/sweep profiles.",
    "DETAIL_STATUS_CLASS": "status-warn",
    "DETAIL_STATUS": "needs review",
    "DETAIL_EVIDENCE": "Check detail contact sheet.",
    "DETAIL_REPAIR": "Add or rebalance feature families.",
    "MANUFACTURING_STATUS_CLASS": "status-warn",
    "MANUFACTURING_STATUS": "needs review",
    "MANUFACTURING_EVIDENCE": "Check section view and facts.",
    "MANUFACTURING_REPAIR": "Adjust wall thickness and gaps.",
    "REFERENCE_STATUS_CLASS": "status-warn",
    "REFERENCE_STATUS": "needs review",
    "REFERENCE_EVIDENCE": "Compare reference_sources, visual checklist, and object-agnostic dimensions.",
    "REFERENCE_REPAIR": "Acquire more references or carry limitation into remaining_gap.",
    "GATE_STATUS_CLASS": "status-warn",
    "GATE_STATUS": "needs review",
    "GATE_EVIDENCE": "Compare review_packet.json against phase_gate.json.",
    "GATE_REPAIR": "Repair or refine required fail/partial/unknown tests.",
    "PRIMITIVE_STATUS_CLASS": "status-warn",
    "PRIMITIVE_STATUS": "needs review",
    "PRIMITIVE_EVIDENCE": "Inspect geometry_quality_metrics.primitive_stack_risk.",
    "PRIMITIVE_REPAIR": "Replace high-risk primitive stack with profile/loft/sweep/revolve strategy.",
    "INTERPENETRATION_STATUS_CLASS": "status-warn",
    "INTERPENETRATION_STATUS": "needs audit",
    "INTERPENETRATION_EVIDENCE": "Inspect all primary views for unintended overlaps.",
    "INTERPENETRATION_REPAIR": "Map overlap to source feature and repair.",
    "FLOATING_STATUS_CLASS": "status-warn",
    "FLOATING_STATUS": "needs audit",
    "FLOATING_EVIDENCE": "Inspect attachments and support surfaces.",
    "FLOATING_REPAIR": "Add connector, bracket, or corrected transform.",
    "DISCONNECTED_STATUS_CLASS": "status-warn",
    "DISCONNECTED_STATUS": "needs audit",
    "DISCONNECTED_EVIDENCE": "Check component counts and unclassified solids in geometry_facts.",
    "DISCONNECTED_REPAIR": "Fuse, attach, classify, or remove orphan components.",
    "MISALIGNMENT_STATUS_CLASS": "status-warn",
    "MISALIGNMENT_STATUS": "needs audit",
    "MISALIGNMENT_EVIDENCE": "Check axes, arrays, symmetry, seams, and controls.",
    "MISALIGNMENT_REPAIR": "Correct reference coordinate or array point.",
    "BAD_CONTACT_STATUS_CLASS": "status-warn",
    "BAD_CONTACT_STATUS": "needs audit",
    "BAD_CONTACT_EVIDENCE": "Check intended contact and clearance relationships.",
    "BAD_CONTACT_REPAIR": "Adjust offsets, clearances, or mating geometry.",
    "COPLANAR_STATUS_CLASS": "status-warn",
    "COPLANAR_STATUS": "needs audit",
    "COPLANAR_EVIDENCE": "Check panels, seams, decals, and thin strips.",
    "COPLANAR_REPAIR": "Offset or cut features to remove ambiguous overlap.",
    "IMPOSSIBLE_ASSEMBLY_STATUS_CLASS": "status-warn",
    "IMPOSSIBLE_ASSEMBLY_STATUS": "needs audit",
    "IMPOSSIBLE_ASSEMBLY_EVIDENCE": "Check handles, pipes, trays, buttons, covers, and sockets.",
    "IMPOSSIBLE_ASSEMBLY_REPAIR": "Add plausible joint, socket, fastener, or support.",
    "OCCLUDED_STATUS_CLASS": "status-warn",
    "OCCLUDED_STATUS": "needs audit",
    "OCCLUDED_EVIDENCE": "Check whether required features are visible and inspectable.",
    "OCCLUDED_REPAIR": "Expose, relocate, or remove blocked feature.",
    "SCALE_STATUS_CLASS": "status-warn",
    "SCALE_STATUS": "needs audit",
    "SCALE_EVIDENCE": "Check small feature size against neighboring parts.",
    "SCALE_REPAIR": "Resize feature family or supporting geometry.",
    "VIEW_INCONSISTENCY_STATUS_CLASS": "status-warn",
    "VIEW_INCONSISTENCY_STATUS": "needs audit",
    "VIEW_INCONSISTENCY_EVIDENCE": "Compare front, side, top, and iso views.",
    "VIEW_INCONSISTENCY_REPAIR": "Repair transform or source feature placement.",
    "DECORATIVE_STATUS_CLASS": "status-warn",
    "DECORATIVE_STATUS": "needs audit",
    "DECORATIVE_EVIDENCE": "Check required functional features against cad_refs and functional review.",
    "DECORATIVE_REPAIR": "Add mechanism, clearance, contact, or load-path geometry.",
    "REFERENCE_MISMATCH_STATUS_CLASS": "status-warn",
    "REFERENCE_MISMATCH_STATUS": "needs audit",
    "REFERENCE_MISMATCH_EVIDENCE": "Compare views against reference_visual_checklist.",
    "REFERENCE_MISMATCH_REPAIR": "Repair silhouette, topology, or signature features.",
    "UNRESOLVED_GATE_STATUS_CLASS": "status-warn",
    "UNRESOLVED_GATE_STATUS": "needs audit",
    "UNRESOLVED_GATE_EVIDENCE": "Inspect review_packet.json for fail/partial/unknown required tests.",
    "UNRESOLVED_GATE_REPAIR": "Repair current phase before advancing.",
    "PRIMITIVE_STACK_STATUS_CLASS": "status-warn",
    "PRIMITIVE_STACK_STATUS": "needs audit",
    "PRIMITIVE_STACK_EVIDENCE": "Check geometry_quality_metrics primitive_stack_risk.",
    "PRIMITIVE_STACK_REPAIR": "Move to surface_refine with profile-driven geometry.",
})
```

## CadQuery Feature Pattern

```python
def build_base_body():
    return (
        cq.Workplane("XY")
        .box(80, 50, 10)
        .edges("|Z")
        .fillet(2)
    )

base, validation = feature_transaction(
    "BaseBody",
    build_base_body,
    lambda result: validate_result(result, "BaseBody", expected_bbox=[-40, 40, -25, 25, -5, 5]),
)

add_memory({
    "feature": "BaseBody",
    "intent": "primary structural volume",
    "iteration": "iteration_01_prototype",
    "type": "box + edge fillet",
    "depends_on": [],
    "validation": validation,
    "quality_state": "prototype",
})
```
