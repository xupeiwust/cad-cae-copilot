from __future__ import annotations

import json
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_AIENG_SRC = _WORKSPACE_ROOT / "aieng" / "src"
if str(_AIENG_SRC) not in sys.path:
    sys.path.insert(0, str(_AIENG_SRC))

from aieng.converters.assembly_cae import ASSEMBLY_RESULT_MAP_PATH
from aieng.converters.assembly_ir import ASSEMBLY_IR_PATH, CONVERSION_MANIFEST_PATH

FIXTURE_DIR = Path(__file__).with_name("fixtures") / "assembly_topopt_demo"
SELECTED_PART_ID = "bracket"
FROZEN_PART_IDS = {"wall", "load_jig"}
PROCESS_ARTIFACTS = {
    "diagnostics/assembly_validation.json",
    "assembly/part_registry.json",
    "assembly/connection_graph.json",
    "assembly/interface_resolution.json",
    "diagnostics/assembly_connection_geometry.json",
    "simulation/assembly_cae_setup_draft.json",
    "simulation/assembly_cae_model.json",
    "diagnostics/assembly_result_mapping.json",
}
SETUP_ARTIFACTS = {
    "analysis/assembly_topopt_problem.json",
    "analysis/topology_optimization_problem.json",
    "diagnostics/assembly_topopt_derivation.json",
}
VERIFICATION_ARTIFACTS = {
    "diagnostics/assembly_post_optimization_verification.json",
    "analysis/assembly_optimization_summary.json",
}


def _load_json(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def load_demo_inputs(*, safe: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    assembly = deepcopy(_load_json("assembly_ir.json"))
    topology_by_part = deepcopy(_load_json("topology_by_part.json"))
    result_map = deepcopy(_load_json("assembly_result_map.json"))
    if safe:
        return assembly, topology_by_part, result_map

    assembly["parts"] = [part for part in assembly["parts"] if part.get("id") != "load_jig"]
    assembly["interfaces"] = [
        iface
        for iface in assembly["interfaces"]
        if iface.get("id") not in {"if_load", "if_jig"}
    ]
    assembly["connections"] = [conn for conn in assembly["connections"] if conn.get("id") != "c_load"]
    assembly["analysis_intent"]["frozen_parts"] = ["wall"]
    topology_by_part.pop("load_jig", None)
    result_map["mapped_results"] = [
        entry
        for entry in result_map.get("mapped_results", [])
        if entry.get("connection_id") != "c_load"
    ]
    return assembly, topology_by_part, result_map


def write_demo_package(
    package_path: Path,
    *,
    safe: bool = True,
    include_result_map: bool = True,
) -> dict[str, Any]:
    assembly, topology_by_part, result_map = load_demo_inputs(safe=safe)
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "assembly-topopt-demo", "resources": {}}))
        zf.writestr(ASSEMBLY_IR_PATH, json.dumps(assembly))
        zf.writestr(CONVERSION_MANIFEST_PATH, json.dumps({"format": "aieng.conversion_manifest"}))
        for part_id, doc in topology_by_part.items():
            zf.writestr(f"parts/{part_id}/topology_map.json", json.dumps(doc))
        if include_result_map:
            zf.writestr(ASSEMBLY_RESULT_MAP_PATH, json.dumps(result_map))
    return {
        "assembly": assembly,
        "topology_by_part": topology_by_part,
        "result_map": result_map if include_result_map else None,
        "package_path": package_path,
    }


def expected_run_artifacts(selected_part_id: str = SELECTED_PART_ID) -> set[str]:
    return {
        "analysis/assembly_topology_optimization.json",
        "diagnostics/assembly_topopt_execution.json",
        "diagnostics/assembly_post_optimization_verification.json",
        "analysis/assembly_optimization_summary.json",
        f"parts/{selected_part_id}/analysis/topology_optimization.json",
        f"parts/{selected_part_id}/geometry/optimized_shape_ir.json",
    }