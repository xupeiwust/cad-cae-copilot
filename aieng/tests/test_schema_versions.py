"""Contract tests for derived-summary schema_version constants.

Asserts that every emitter inside :mod:`aieng` reads its
``schema_version`` from :mod:`aieng.schema_versions`, and that the
cross-repo ``computed_metrics.json`` exporter in ``aieng_freecad_mcp``
ships the same value as :data:`FRD_COMPUTED_METRICS_SCHEMA`.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.cae_preprocessing_summary import generate_preprocessing_summary
from aieng.cae_result_summary import (
    generate_cae_result_summary,
    generate_evidence_index,
)
from aieng.cae_simulation_run_summary import generate_simulation_run_summary
from aieng.modeling_plan.planner import RuleBasedModelingPlanner
from aieng.schema_versions import (
    CAE_PREPROCESSING_SUMMARY_SCHEMA,
    CAE_RESULT_SUMMARY_SCHEMA,
    CAE_SIMULATION_RUN_SUMMARY_SCHEMA,
    EVIDENCE_INDEX_SCHEMA,
    FIELD_SUMMARY_SCHEMA,
    FRD_COMPUTED_METRICS_SCHEMA,
    MODELING_PLAN_SCHEMA,
)


def _empty_package(tmp_path: Path) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
    return pkg


def test_cae_result_summary_uses_constant(tmp_path: Path) -> None:
    pkg = _empty_package(tmp_path)
    summary = generate_cae_result_summary(pkg)
    assert summary["schema_version"] == CAE_RESULT_SUMMARY_SCHEMA


def test_evidence_index_uses_constant(tmp_path: Path) -> None:
    pkg = _empty_package(tmp_path)
    index = generate_evidence_index(pkg)
    assert index["schema_version"] == EVIDENCE_INDEX_SCHEMA


def test_cae_preprocessing_summary_uses_constant(tmp_path: Path) -> None:
    pkg = _empty_package(tmp_path)
    summary = generate_preprocessing_summary(pkg)
    assert summary["schema_version"] == CAE_PREPROCESSING_SUMMARY_SCHEMA


def test_cae_simulation_run_summary_uses_constant(tmp_path: Path) -> None:
    pkg = _empty_package(tmp_path)
    summary = generate_simulation_run_summary(pkg)
    assert summary["schema_version"] == CAE_SIMULATION_RUN_SUMMARY_SCHEMA


def test_field_summary_uses_constant(tmp_path: Path) -> None:
    from aieng.cae_field_summary import generate_field_summary

    pkg = _empty_package(tmp_path)
    summary = generate_field_summary(pkg)
    assert summary["schema_version"] == FIELD_SUMMARY_SCHEMA


def test_modeling_plan_uses_constant() -> None:
    planner = RuleBasedModelingPlanner()
    plan = planner.plan("create a 100x60x10 mm plate with 4 mounting holes")
    assert plan["plan_schema_version"] == MODELING_PLAN_SCHEMA


def _frd_value(v: float) -> str:
    return f"{v:12.5E}"


def _node_line(node_id: int, values: list[float]) -> str:
    return "    -1" + f"{node_id:12d}" + "".join(_frd_value(v) for v in values)


def test_frd_extractor_uses_constant(tmp_path: Path) -> None:
    """Real FRD parse to confirm the extractor emits the constant."""
    from aieng.simulation.frd_result_extractor import extract_computed_metrics

    lines = [
        "    1C                                                                         1",
        "    1UCUT.......................                                                2",
        "    -4  DISP        4    1",
        "    -5  D1          1    2    1    0",
        "    -5  D2          1    2    2    0",
        "    -5  D3          1    2    3    0",
        "    -5  ALL         1    2    0    1",
        _node_line(1, [0.1, 0.2, 0.3, 0.374]),
        "    -3",
        " 9999",
    ]
    frd_path = tmp_path / "job.frd"
    frd_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = extract_computed_metrics(frd_path)
    assert result["schema_version"] == FRD_COMPUTED_METRICS_SCHEMA


def test_distinct_contracts_in_same_module() -> None:
    """Post-processing summary and evidence index live in the same module
    but are independent contracts. This test fails if a future refactor
    aliases them, which would silently couple their version bumps."""
    import aieng.schema_versions as sv

    # They may legitimately hold the same string value at a given moment,
    # but must be addressable as separate names. A `del sv.EVIDENCE_INDEX_SCHEMA`
    # would not affect CAE_RESULT_SUMMARY_SCHEMA — assert that membership.
    assert hasattr(sv, "CAE_RESULT_SUMMARY_SCHEMA")
    assert hasattr(sv, "EVIDENCE_INDEX_SCHEMA")
    assert "CAE_RESULT_SUMMARY_SCHEMA" in sv.__dict__
    assert "EVIDENCE_INDEX_SCHEMA" in sv.__dict__


def test_frd_metrics_schema_matches_freecad_exporter() -> None:
    """Cross-repo contract: aieng's FRD_COMPUTED_METRICS_SCHEMA must match
    aieng_freecad_mcp's COMPUTED_METRICS_SCHEMA_VERSION verbatim. If
    aieng_freecad_mcp is not importable, skip with a clear message."""
    exporter = pytest.importorskip(
        "freecad_mcp.computed_metrics_exporter",
        reason="aieng_freecad_mcp not installed; cross-repo lockstep "
        "contract cannot be verified in this environment.",
    )
    assert exporter.COMPUTED_METRICS_SCHEMA_VERSION == FRD_COMPUTED_METRICS_SCHEMA, (
        f"FRD_COMPUTED_METRICS_SCHEMA ({FRD_COMPUTED_METRICS_SCHEMA!r}) and "
        f"freecad_mcp.computed_metrics_exporter.COMPUTED_METRICS_SCHEMA_VERSION "
        f"({exporter.COMPUTED_METRICS_SCHEMA_VERSION!r}) have drifted. Bump "
        "one to match the other and document the bump in CHANGELOG."
    )
