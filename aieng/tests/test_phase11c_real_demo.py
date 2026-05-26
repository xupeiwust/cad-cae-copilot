from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_phase11c_scripts_exist():
    assert Path("scripts/generate_real_bracket_step.py").exists()
    assert Path("scripts/run_real_step_demo.py").exists()
    assert Path("scripts/prepare_real_benchmark_pack.py").exists()


def test_phase11c_real_context_fixture_exists():
    path = Path("examples/real_bracket_user_context.yaml")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "material:" in text
    assert "protected_features:" in text
    assert "simulation:" in text


def test_generate_real_bracket_step_help():
    result = subprocess.run(
        [sys.executable, "scripts/generate_real_bracket_step.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "real_bracket.step" in result.stdout


def test_run_real_step_demo_help():
    result = subprocess.run(
        [sys.executable, "scripts/run_real_step_demo.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "build-aag" in result.stdout
    assert "real_bracket.step" in result.stdout


def test_prepare_real_benchmark_pack_help():
    result = subprocess.run(
        [sys.executable, "scripts/prepare_real_benchmark_pack.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "real_bracket_001" in result.stdout


def test_real_benchmark_run_scaffold_exists():
    root = Path("benchmark_runs/real_bracket_001")
    assert root.is_dir()
    for name in [
        "README.md",
        "results_run_001.md",
        "instructions.md",
        "raw_step_input_spec.md",
        "aieng_input_index.md",
        "questions.md",
        "scoring_sheet.md",
        "expected_observations.md",
    ]:
        assert (root / name).exists(), f"missing {name}"


def test_real_benchmark_scaffold_mentions_conditions_and_aag():
    instructions = Path("benchmark_runs/real_bracket_001/instructions.md").read_text(encoding="utf-8")
    index_text = Path("benchmark_runs/real_bracket_001/aieng_input_index.md").read_text(encoding="utf-8")
    assert "Condition A" in instructions
    assert "Condition B" in instructions
    assert "README_FOR_AI.md" in index_text
    assert "graph/aag.json" in index_text


def test_real_benchmark_results_record_has_conservative_policy():
    text = Path("benchmark_runs/real_bracket_001/results_run_001.md").read_text(encoding="utf-8")
    assert "No solver result exists." in text
    assert "No mesh was generated." in text
    assert "No geometry was modified." in text
    assert "Feature recognition remains candidate-level" in text
    assert "No engineering safety claim is made." in text


def test_real_benchmark_results_record_does_not_claim_scored_session():
    text = Path("benchmark_runs/real_bracket_001/results_run_001.md").read_text(encoding="utf-8")
    assert "No external AI scoring session was run in Phase 11D" in text
    assert "not scored" in text


def test_docs_mention_phase11c():
    # Phase identifiers moved from README into development_log.md when
    # the outward-facing README was created. The roadmap and
    # mvp_checkpoint references still hold.
    assert "11C" in Path("docs/development_log.md").read_text(encoding="utf-8")
    assert "11C" in Path("docs/roadmap.md").read_text(encoding="utf-8")
    assert "11C" in Path("docs/mvp_checkpoint.md").read_text(encoding="utf-8")
    benchmark_doc = Path("docs/ai_understanding_benchmark.md").read_text(encoding="utf-8")
    assert "real_bracket_001" in benchmark_doc


def test_real_step_fixture_policy():
    real_step = Path("examples/real_bracket.step")
    if real_step.exists():
        assert real_step.stat().st_size > 0
        return

    generator = Path("scripts/generate_real_bracket_step.py").read_text(encoding="utf-8")
    assert "examples/real_bracket.step" in generator


@pytest.mark.skipif(
    not Path("examples/real_bracket.step").exists(),
    reason="real STEP fixture not present in repository",
)
def test_real_step_demo_script_mentions_occ_backend_when_fixture_present():
    text = Path("scripts/run_real_step_demo.py").read_text(encoding="utf-8")
    assert "--backend" in text
    assert "occ" in text
    assert "build-aag" in text
