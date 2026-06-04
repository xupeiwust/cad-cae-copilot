"""JSON Schemas for high-frequency runtime tools.

Hand-written so MCP clients (Claude Code, Cursor, Cline, etc.) and the
in-process agent harness can produce valid tool calls. Schemas follow JSON
Schema draft-7 + the MCP convention of returning a single object at the
top level.

A tool not listed here falls back to a permissive ``{"type": "object"}``
schema in ``runtime.list_tools_for_mcp()``.

Adding a new schema is a one-line entry in ``TOOL_SCHEMAS``; keep schemas
minimal and pragmatic — describe the parameters the LLM actually needs to
get right, not every internal flag.
"""

from __future__ import annotations

from typing import Any


def _project_id_schema(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reusable schema for tools that only need a project_id."""
    schema: dict[str, Any] = {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Workbench project ID (UUID-style).",
            },
        },
        "additionalProperties": True,
    }
    if extra:
        schema["properties"].update(extra.get("properties", {}))
        schema["required"] = list(set(schema["required"] + (extra.get("required") or [])))
    return schema


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    # ── agent onboarding ──────────────────────────────────────────────────────
    "aieng.list_projects": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "No parameters required. Returns all known projects.",
    },
    "aieng.agent_readme": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "No parameters required. Returns AGENTS.md content.",
    },
    "aieng.delete_project": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string", "description": "Project id to permanently delete."},
        },
        "additionalProperties": True,
        "description": "Permanently delete a project (its directory + chat sessions). Approval required.",
    },
    "aieng.apply_shape_ir_patch": {
        "type": "object",
        "required": ["project_id", "patch"],
        "properties": {
            "project_id": {"type": "string"},
            "patch": {
                "type": "object",
                "description": (
                    "Shape IR patch: {operations: [...]}. Each op has 'op' (set_parameter | "
                    "move_control_point | add_node | remove_node | replace_node | connect | "
                    "disconnect | change_representation_backend) plus its fields (target, "
                    "parameter, path, value/delta, node, connection, value) and optional 'reason'. "
                    "Applied atomically against geometry/shape_ir.json; on success the package is "
                    "recompiled through runtime routing."
                ),
            },
            "dry_run": {
                "type": "boolean",
                "description": "Validate + report the patch without writing or recompiling (default false).",
            },
        },
        "additionalProperties": True,
        "description": "Apply a surgical patch to a project's Shape IR (atomic, validated, recompiled).",
    },
    "opt.run_topology_optimization": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "problem": {
                "type": "object",
                "description": (
                    "Topology optimization problem: grid {nelx, nely}, volfrac, penalty, rmin, "
                    "max_iters, bcs {preset: cantilever|mbb_beam, OR supports/loads cell lists}, "
                    "optional design_space_node. For optimizer=precomputed, pass a 2D 'density' "
                    "grid. Omit problem (or set auto_derive) to derive it from the CAE setup."
                ),
            },
            "auto_derive": {
                "type": "boolean",
                "description": (
                    "Derive supports/loads/design-space from the project's CAE setup + geometry "
                    "(via opt.derive_problem_from_cae) before solving. Implied when problem is omitted; "
                    "any provided problem fields override the derived ones."
                ),
            },
            "dimension": {
                "type": "string",
                "enum": ["2d", "3d"],
                "description": (
                    "Problem dimension for auto_derive (default 2d). 3d uses the experimental "
                    "structured-voxel simp_3d optimizer and a full-3D derivation (no projection); "
                    "if BCs can't be safely mapped it returns status=needs_user_input. Implied 3d "
                    "when optimizer=simp_3d."
                ),
            },
            "optimizer": {
                "type": "string",
                "description": (
                    "Optimizer backend (default simp_2d, or simp_3d when dimension=3d). simp_3d is "
                    "experimental/structured-voxel/not-production. Unknown names fall back to simp_2d."
                ),
            },
        },
        "additionalProperties": True,
        "description": (
            "Run topology optimization (built-in self-contained 2D SIMP, compliance "
            "minimization). Writes analysis/topology_optimization.json. No external solver."
        ),
    },
    "opt.derive_problem_from_cae": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "dimension": {"type": "string", "enum": ["2d", "3d"],
                          "description": "2d (default) projects to a plane; 3d builds a structured voxel grid (no projection). 3d returns status=needs_user_input if BCs can't be safely mapped."},
            "resolution": {"type": "integer", "description": "2D: cells along the longest design-space axis (default 48)."},
            "resolution_3d": {"type": "integer", "description": "3D: voxels along the longest axis (default 16) — keep small."},
            "volfrac": {"type": "number", "description": "Target volume fraction (default 0.5; 0.3 for 3d)."},
            "penalty": {"type": "number", "description": "SIMP penalization exponent (default 3.0)."},
            "rmin": {"type": "number", "description": "Sensitivity filter radius in cells (default 1.5)."},
            "max_iters": {"type": "integer", "description": "Optimizer iteration cap (default 40; 30 for 3d)."},
        },
        "additionalProperties": True,
        "description": (
            "Derive a topology-optimization problem (grid + supports + loads + design space) from "
            "the project's CAE setup + geometry. dimension=2d (default) projects to a plane; 3d "
            "keeps the full 3D layout. Read-only; returns problem + derivation (or needs_user_input)."
        ),
    },
    "opt.writeback_to_shape_ir": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "method": {
                "type": "string",
                "enum": ["contour", "voxels", "surface", "smooth_mesh", "marching_cubes"],
                "description": (
                    "Geometry for the optimized body. 2D: 'contour' (default) = smooth "
                    "marching-squares boundary, extruded; 'voxels' = blocky cells. 3D: "
                    "'surface'/'smooth_mesh'/'marching_cubes' (default) = smooth marching-cubes "
                    "mesh proxy (a smooth_mesh_proxy node); 'voxels' = blocky voxel union. 3D "
                    "outputs are mesh / lossy / preview-only / not production CAD (no B-Rep)."
                ),
            },
            "boundary": {
                "type": "string",
                "enum": ["spline", "polygon"],
                "description": (
                    "For method=contour, how boundary loops are interpreted: 'spline' "
                    "(default) = closed periodic spline (CAD-friendly curve / clean NURBS "
                    "edge in B-Rep, densified smooth polygon in mesh); 'polygon' = straight "
                    "segments."
                ),
            },
            "representation": {
                "type": "string",
                "description": (
                    "Compile target for the optimized body. Default brep_build123d -> "
                    "analytic faces an engineer can pick / export to STEP / feed back into "
                    "CAD/CAE; manifold_mesh -> watertight mesh (also the auto-fallback if "
                    "the B-Rep build fails to execute)."
                ),
            },
            "cell_size": {
                "type": "array",
                "items": {"type": "number"},
                "description": "In-plane voxel cell size [sx, sy] in mm (default [1, 1]).",
            },
            "thickness": {"type": "number", "description": "Extrusion depth in Z (default = larger cell edge)."},
            "origin": {"type": "array", "items": {"type": "number"}, "description": "Field origin [x, y, z]."},
            "node_id": {"type": "string", "description": "Override the generated Shape IR node id."},
        },
        "additionalProperties": True,
        "description": (
            "Author the topology-optimization result back into geometry/shape_ir.json as one "
            "density_voxels node and recompile. Run opt.run_topology_optimization first."
        ),
    },
    "opt.run_assembly_topology_optimization": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "optimizer": {
                "type": "string",
                "description": "Optimizer backend. Defaults to simp_2d or simp_3d from the derived problem dimension.",
            },
            "writeback": {
                "type": "boolean",
                "description": "Write a selected-part derived optimized Shape IR artifact when safe (default true).",
            },
            "method": {
                "type": "string",
                "enum": ["contour", "voxels", "surface", "smooth_mesh", "marching_cubes"],
                "description": "Selected-part writeback geometry method. Defaults to contour for 2D and smooth_mesh for 3D.",
            },
            "representation": {
                "type": "string",
                "description": "Selected-part derived Shape IR representation. Defaults to brep_build123d for 2D and manifold_mesh for 3D.",
            },
            "boundary": {
                "type": "string",
                "enum": ["spline", "polygon"],
                "description": "2D contour boundary style for selected-part writeback (default spline).",
            },
        },
        "additionalProperties": True,
        "description": (
            "Explicitly run assembly-aware topology optimization for one selected design part. "
            "Consumes analysis/assembly_topopt_problem.json and analysis/topology_optimization_problem.json, "
            "calls the existing optimizer, writes assembly diagnostics/provenance, and creates selected-part "
            "derived artifacts without overwriting package-level geometry or reference parts."
        ),
    },
    "cae.map_results": {
        "type": "object",
        "required": ["project_id"],
        "properties": {"project_id": {"type": "string"}},
        "additionalProperties": True,
        "description": (
            "Map CAE results (computed_metrics + field_regions) back to topology "
            "entities, object_registry objects, and source_ir_node. Writes "
            "analysis/cae_result_map.json. Read-only analysis (no solver)."
        ),
    },
    "aieng.find_projects_by_part": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Substring matched case-insensitively against named-part labels, "
                    "e.g. 'optimus', 'bracket', 'mounting_hole'."
                ),
            },
        },
        "additionalProperties": True,
        "description": "Find projects whose geometry contains a named part matching the query.",
    },

    # ── read-only inspection ──────────────────────────────────────────────────
    "aieng.inspect_package": _project_id_schema(),
    "aieng.agent_context": _project_id_schema(),
    "aieng.read_audit_log": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "description": "Max number of audit entries to return (default 50).",
            },
        },
        "additionalProperties": True,
    },
    "aieng.validate": _project_id_schema(),
    "aieng.write_completeness_report": _project_id_schema(),
    "aieng.update_validation_status": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "status": {
                "type": "object",
                "description": "Per-category validation status fields to merge.",
            },
        },
        "additionalProperties": True,
    },

    # ── conversion ────────────────────────────────────────────────────────────
    "aieng.convert": {
        "type": "object",
        "required": ["project_id", "sourcePath"],
        "properties": {
            "project_id": {"type": "string"},
            "sourcePath": {
                "type": "string",
                "description": "Absolute path to a .step / .stp / .FCStd / .shape.json / .shape_ir.json source file to import.",
            },
            "executeShapeIr": {
                "type": "boolean",
                "description": "For Shape IR sources, execute the generated build123d source and publish a viewer preview (default true).",
            },
        },
        "additionalProperties": True,
    },

    # ── CAD generation (agent writes the code, we execute) ───────────────────
    "cad.execute_build123d": {
        "type": "object",
        "required": ["project_id", "code"],
        "properties": {
            "project_id": {"type": "string"},
            "name": {
                "type": "string",
                "description": (
                    "Optional human-recognizable project name (e.g. 'Optimus + Bumblebee'). "
                    "Set this so the project is findable in list_projects instead of staying "
                    "the default 'STEP workbench project'. If omitted, a placeholder-named "
                    "project is auto-named from its part labels."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "Full build123d Python script. Must bind the final model to a "
                    "variable named `result`. Do NOT include export calls — the runner "
                    "adds them. To name parts so you can reference them later, set "
                    "`.label` on shapes and combine with Compound, e.g. "
                    "`fl = Cylinder(3, 30); fl.label = 'motor_pod_FL'; "
                    "result = Compound(children=[body, fl])` — labels appear as named "
                    "parts in topology_map and feature_graph. "
                    "Also set `.color = Color(r, g, b)` (RGB in 0..1) on each part — "
                    "colors render in the multi-view thumbnail AND travel through to "
                    "the GLB that the UI viewer shows, so a user looking at the model "
                    "sees the colors you assigned. "
                    "In mode=append, the previous model is available as `previous_result`."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["replace", "append"],
                "description": (
                    "replace (default): the script defines the whole model. "
                    "append: the previously-stored script runs first and its model is "
                    "exposed as `previous_result`; your code then adds to it and must "
                    "still reassign `result` (e.g. "
                    "`result = Compound(children=[previous_result, new_part])`). "
                    "Append requires an existing model — run once with replace first."
                ),
            },
            "write_files": {
                "type": "boolean",
                "description": "Write artifacts into the .aieng package (default true).",
            },
            "model_kind": {
                "type": "string",
                "enum": ["auto", "organic", "mechanical"],
                "description": (
                    "Gates the feature-graph heuristics (default auto). "
                    "'mechanical' runs bolt-pattern + base-plate detection; "
                    "'organic' skips them (use for characters/vehicles/products, "
                    "where those heuristics mislabel limb cylinders as mounting holes). "
                    "'auto' infers from part labels and whether the organic helpers "
                    "(lofted_stack/capsule/…) are used."
                ),
            },
            "timeout": {
                "type": "integer",
                "minimum": 1,
                "maximum": 600,
                "description": "Subprocess timeout in seconds (default 60).",
            },
            "thumbnail": {
                "type": "boolean",
                "description": (
                    "Return a rendered PNG so you can visually verify the geometry "
                    "(default true). The image is a 2x2 contact sheet with four "
                    "labelled views: front, side, top, iso — each catches problems "
                    "the others hide (alignment in front, depth in side, layout in "
                    "top, overall form in iso). Per-part `.color` values applied to "
                    "build123d shapes are honored. The MCP client receives this as an "
                    "image content block. Set false to skip rendering."
                ),
            },
        },
        "additionalProperties": True,
    },

    # ── CAD skill planner (read-only, agent-orchestrated) ───────────────────
    "cad.plan_build123d_skill": {
        "type": "object",
        "required": ["project_id", "message"],
        "properties": {
            "project_id": {"type": "string"},
            "message": {
                "type": "string",
                "description": "Natural-language CAD request to route through a deterministic CAD skill template.",
            },
            "outer_diameter_mm": {
                "type": "number",
                "description": "Optional explicit flange outside diameter override.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Optional explicit flange thickness override.",
            },
            "center_bore_diameter_mm": {
                "type": "number",
                "description": "Optional explicit center bore diameter override.",
            },
            "bolt_circle_diameter_mm": {
                "type": "number",
                "description": "Optional explicit bolt pitch-circle diameter override.",
            },
            "bolt_hole_diameter_mm": {
                "type": "number",
                "description": "Optional explicit bolt through-hole diameter override.",
            },
            "bolt_hole_count": {
                "type": "integer",
                "minimum": 2,
                "maximum": 16,
                "description": "Optional explicit bolt-hole count override.",
            },
        },
        "additionalProperties": True,
    },

    # ── Reference image attach (per-project, used by thumbnails) ─────────────
    "cad.set_reference_image": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "image_url": {
                "type": "string",
                "description": (
                    "HTTP(S) URL of a reference image (jpg/png/webp). Fetched "
                    "server-side, downscaled to fit 800x800, and stored as "
                    "geometry/reference.png in the .aieng package. Either "
                    "image_url or image_path is required."
                ),
            },
            "image_path": {
                "type": "string",
                "description": (
                    "Local file path to a reference image. Use when the image "
                    "is on the workbench host, e.g. /tmp/optimus_ref.jpg."
                ),
            },
            "description": {
                "type": "string",
                "description": "Short caption for the reference, stored in geometry/reference.json.",
            },
        },
        "additionalProperties": True,
    },

    # ── Critique: deterministic engineering audit (read-only) ───────────────
    "cad.critique": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["auto", "engineering", "geometry"],
                "description": (
                    "auto (default): geometry sanity + engineering audit when the "
                    "model has canonically-labelled engineering features (rib/"
                    "base_plate/mounting_hole/...). engineering: force the "
                    "manufacturing audit. geometry: only basic sanity checks "
                    "(component counts, floating components)."
                ),
            },
            "min_wall_mm": {
                "type": "number",
                "description": "Override min wall thickness rule (default 3mm = CNC aluminium).",
            },
            "min_corner_radius_mm": {
                "type": "number",
                "description": "Override min internal corner radius rule (default 2mm).",
            },
        },
        "additionalProperties": True,
    },

    # ── CAD source readback (read-only) ──────────────────────────────────────
    "cad.get_source": _project_id_schema(),
    "cad.list_editable_parameters": _project_id_schema(),
    "cad.get_named_part_bbox": {
        "type": "object",
        "required": ["project_id", "part_name"],
        "properties": {
            "project_id": {"type": "string"},
            "part_name": {
                "type": "string",
                "description": "Exact named-part label from geometry/topology_map.json, e.g. 'thigh_L'.",
            },
        },
        "additionalProperties": True,
    },
    "cad.refine": {
        "type": "object",
        "required": ["project_id", "feedback"],
        "properties": {
            "project_id": {"type": "string"},
            "feedback": {
                "type": "string",
                "description": "Natural-language change request, e.g. 'move thigh_L down by 20mm'.",
            },
            "write_files": {
                "type": "boolean",
                "description": "Write refined geometry/source/topology artifacts back into the package (default true).",
            },
            "timeout": {
                "type": "integer",
                "minimum": 1,
                "maximum": 600,
                "description": "Subprocess timeout in seconds for the refined build123d execution (default 60).",
            },
        },
        "additionalProperties": True,
    },

    # ── CAD edit (approval-gated) ────────────────────────────────────────────
    "cad.edit_parameter": {
        "type": "object",
        "required": ["project_id", "featureId", "parameterName", "newValue"],
        "properties": {
            "project_id": {"type": "string"},
            "featureId": {
                "type": "string",
                "description": "Feature ID (matches @feature: pointers, e.g. 'feat_hole_pattern_001').",
            },
            "parameterName": {
                "type": "string",
                "description": "Parameter name on the feature, e.g. 'hole_diameter_mm'.",
            },
            "newValue": {
                "description": "Replacement value. Type follows the parameter's declared schema (number, string, bool).",
            },
        },
        "additionalProperties": True,
    },
    "cad.remove_part": {
        "type": "object",
        "required": ["project_id", "label"],
        "properties": {
            "project_id": {"type": "string"},
            "label": {
                "type": "string",
                "description": "build123d .label of the named part to remove (e.g. 'chest_plate').",
            },
            "timeout": {"type": "integer", "minimum": 1, "maximum": 600},
        },
        "additionalProperties": True,
    },
    "cad.replace_part": {
        "type": "object",
        "required": ["project_id", "label", "code"],
        "properties": {
            "project_id": {"type": "string"},
            "label": {
                "type": "string",
                "description": "build123d .label of the named part to replace (e.g. 'head').",
            },
            "code": {
                "type": "string",
                "description": (
                    "Replacement build123d code. Must reassign `result` to the new "
                    "part and set its .label (normally back to the same name). "
                    "Omit export calls. The high-level helpers (lofted_stack, capsule, "
                    "etc.) are available."
                ),
            },
            "timeout": {"type": "integer", "minimum": 1, "maximum": 600},
        },
        "additionalProperties": True,
    },

    # ── CAE setup / solver pipeline ──────────────────────────────────────────
    "cae.apply_setup_patch": {
        "type": "object",
        "anyOf": [
            {"required": ["project_id", "patches"]},
            {"required": ["project_id", "patch"]},
        ],
        "properties": {
            "project_id": {"type": "string"},
            "patches": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "object"},
                "description": (
                    "Preferred input. Array of CAE setup patch operations "
                    "(create_file / replace_json / merge_object / append_array_item) "
                    "with target path and payload."
                ),
            },
            "patch": {
                "type": "object",
                "description": (
                    "Legacy compatibility input. Either one CAE setup patch object, or "
                    "a map of operation-name keys to patch objects. Prefer 'patches'."
                ),
            },
        },
        "additionalProperties": True,
    },
    "cae.prepare_solver_run": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "runId": {
                "type": "string",
                "description": "Solver run identifier; created if absent.",
            },
        },
        "additionalProperties": True,
    },
    "cae.generate_solver_input": _project_id_schema(),
    "cae.run_solver": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "runId": {"type": "string"},
            "timeout_s": {"type": "integer", "minimum": 1, "maximum": 3600},
        },
        "additionalProperties": True,
    },
    "cae.extract_solver_results": _project_id_schema(),
    "cae.extract_field_regions": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "field": {
                "type": "string",
                "enum": ["stress", "displacement"],
                "description": "Field to cluster (default 'stress').",
            },
            "max_clusters": {"type": "integer", "minimum": 1, "maximum": 64},
        },
        "additionalProperties": True,
    },

    # ── post-processing ──────────────────────────────────────────────────────
    "postprocess.generate_computed_metrics": {
        "type": "object",
        "required": ["project_id", "inputPath"],
        "properties": {
            "project_id": {"type": "string"},
            "inputPath": {
                "type": "string",
                "description": "Absolute path to a CSV or JSON file with the computed metrics.",
            },
            "loadCaseId": {"type": "string"},
            "software": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "postprocess.refresh_cae_summary": _project_id_schema(),

    # ── preview / runtime introspection ──────────────────────────────────────
    "aieng.generate_preview": {
        "type": "object",
        "required": ["project_id"],
        "properties": {
            "project_id": {"type": "string"},
            "format": {"type": "string", "enum": ["glb", "stl"]},
        },
        "additionalProperties": True,
    },
    "aieng.refresh_semantics": _project_id_schema(),
}


def get_schema(tool_name: str) -> dict[str, Any] | None:
    """Lookup helper; returns None if no curated schema exists for the tool."""
    return TOOL_SCHEMAS.get(tool_name)
