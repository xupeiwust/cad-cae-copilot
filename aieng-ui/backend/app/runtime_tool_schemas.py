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
                "description": "Absolute path to a .step / .stp source file to import.",
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

    # ── CAD source readback (read-only) ──────────────────────────────────────
    "cad.get_source": _project_id_schema(),
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

    # ── CAE setup / solver pipeline ──────────────────────────────────────────
    "cae.apply_setup_patch": {
        "type": "object",
        "required": ["project_id", "patch"],
        "properties": {
            "project_id": {"type": "string"},
            "patch": {
                "type": "object",
                "description": (
                    "CAE setup patch with operation kind (create_file / replace_json / "
                    "merge_object / append_array_item), target path, and payload."
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
