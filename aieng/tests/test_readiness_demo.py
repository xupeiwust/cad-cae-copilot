"""AI-readability / readiness demo tests (Phase 20)."""
from __future__ import annotations

from pathlib import Path

from aieng.converters.cli_runners import (
    convert_source,
    readiness_report_payload,
    readiness_report_text,
)


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "sample_bracket.FCStd"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_fcstd.py"


def _ensure_fixture() -> Path:
    if not FIXTURE.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_sample_fcstd", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.generate(FIXTURE)
    return FIXTURE


def test_readiness_payload_describes_converter_and_information_state(tmp_path: Path):
    fixture = _ensure_fixture()
    out = tmp_path / "readiness_target.aieng"
    convert_source(
        source_path=fixture,
        out=out,
        model_id="readiness_target",
        converter_id="freecad_reference",
        overwrite=True,
        runtime_mode="offline",
    )
    report = readiness_report_payload(out)
    assert report["model_id"] == "readiness_target"
    assert report["source_mode"] == "converter"
    converter = report["converter"]
    assert converter["converter_id"] == "freecad_reference"
    assert converter["source_system"] == "FreeCAD"
    assert set(converter["achieved_levels"]).issuperset({0, 2, 3})
    # Adaptive coverage_categories must be surfaced in the converter section.
    coverage = {c["category"]: c["status"] for c in converter["coverage_categories"]}
    assert coverage.get("topology") == "missing"
    assert coverage.get("object_registry") == "complete"
    assert coverage.get("writeback_metadata") == "unsupported"
    # Information state buckets must exist and at least the topology things should be missing.
    info = report["information_state"]
    assert "topology" in info["missing"]
    # Boundary reminder is always present.
    assert "does not execute" in report["boundary_reminder"]


def test_readiness_text_renders_recommended_external_actions(tmp_path: Path):
    fixture = _ensure_fixture()
    out = tmp_path / "readiness_text.aieng"
    convert_source(
        source_path=fixture,
        out=out,
        model_id="readiness_text",
        converter_id="freecad_reference",
        overwrite=True,
        runtime_mode="offline",
    )
    text = readiness_report_text(out)
    assert "Readiness report for:" in text
    assert "freecad_reference" in text
    assert "recommended_external_actions:" in text
    # The completeness writer always produces at least one recommended action
    # for a freshly converted package (topology missing -> extract_topology).
    assert "topology" in text
    assert "does not execute" in text


def test_readiness_demo_does_not_change_package(tmp_path: Path):
    fixture = _ensure_fixture()
    out = tmp_path / "readiness_stable.aieng"
    convert_source(
        source_path=fixture,
        out=out,
        model_id="readiness_stable",
        converter_id="freecad_reference",
        overwrite=True,
        runtime_mode="offline",
    )
    before = out.read_bytes()
    _ = readiness_report_payload(out)
    _ = readiness_report_text(out)
    after = out.read_bytes()
    assert before == after, "readiness reports must be read-only"
