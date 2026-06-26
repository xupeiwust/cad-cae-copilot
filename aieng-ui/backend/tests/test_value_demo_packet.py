from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "aieng-ui" / "backend" / "scripts" / "value_demo_packet.py"
RUNBOOK = ROOT / "docs" / "cad-cae-value-demo.md"


def _load_packet_module():
    spec = importlib.util.spec_from_file_location("value_demo_packet", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_value_demo_packet_anchors_real_frd_pipeline_and_honesty_boundaries() -> None:
    module = _load_packet_module()
    packet = module.build_packet()
    markdown = module.build_markdown()

    assert packet["geometry"]["kind"] == "single_connected_solid"
    assert "result = beam" in packet["geometry"]["cad_code"]
    assert "cae.run_simulation_pipeline" in markdown
    assert "report.generate" in markdown
    assert "simulation/runs/value_demo_run_001/outputs/result.frd" in packet["expected_evidence"]
    assert "results/computed_metrics.json" in packet["expected_evidence"]
    assert any("Synthetic fallback fields are a failed demo condition" in item for item in packet["honesty_boundaries"])
    assert any("mesh-dependent" in item for item in packet["honesty_boundaries"])


def test_value_demo_runbook_links_packet_and_forbids_synthetic_success() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "aieng-ui/backend/scripts/value_demo_packet.py" in text
    assert "cae.run_simulation_pipeline" in text
    assert "report.generate" in text
    assert "simulation/runs/value_demo_run_001/outputs/result.frd" in text
    assert "Synthetic fallback fields are a failed demo condition" in text
    assert "Do not invent face" in text
    assert "not certification" in text
