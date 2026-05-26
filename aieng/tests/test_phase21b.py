"""Tests for Phase 21B: run-record structure, HOWTO, and template validation."""
from __future__ import annotations

import json
from pathlib import Path

BENCHMARK_DIR = Path("benchmarks/ai_usefulness")
RESULTS_DIR = BENCHMARK_DIR / "results"
HOWTO = BENCHMARK_DIR / "HOWTO_RUN.md"
TEMPLATE = RESULTS_DIR / "run_record_template.json"
SCHEMA = BENCHMARK_DIR / "results.schema.json"


# ---------------------------------------------------------------------------
# HOWTO_RUN.md — existence and key content
# ---------------------------------------------------------------------------


def test_howto_run_exists():
    assert HOWTO.exists(), "benchmarks/ai_usefulness/HOWTO_RUN.md must exist"
    assert HOWTO.is_file()


def test_howto_run_mentions_leakage_prevention():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "leakage" in text or "cross-condition" in text, (
        "HOWTO_RUN.md must address cross-condition leakage prevention"
    )


def test_howto_run_mentions_fresh_sessions():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "fresh" in text or "new session" in text or "separate" in text, (
        "HOWTO_RUN.md must specify that each condition uses a fresh session"
    )


def test_howto_run_mentions_same_model():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "same model" in text, (
        "HOWTO_RUN.md must state that both conditions use the same model"
    )


def test_howto_run_mentions_temperature():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "temperature" in text or "decoding" in text, (
        "HOWTO_RUN.md must mention recording temperature or decoding settings"
    )


def test_howto_run_mentions_verbatim_questions():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "verbatim" in text or "same questions" in text, (
        "HOWTO_RUN.md must specify asking questions verbatim"
    )


def test_howto_run_warns_single_scenario_not_sufficient():
    text = HOWTO.read_text(encoding="utf-8").lower()
    # Must warn that one scenario is not sufficient for broad conclusions
    warns_single = (
        "one scenario" in text
        or "single scenario" in text
        or "one run" in text
        or "one data point" in text
    )
    warns_insufficient = (
        "not sufficient" in text
        or "not enough" in text
        or "not support broad" in text
        or "one scenario is not" in text
    )
    assert warns_single and warns_insufficient, (
        "HOWTO_RUN.md must warn that one scenario is not sufficient for broad conclusions"
    )


def test_howto_run_mentions_schema_validation():
    text = HOWTO.read_text(encoding="utf-8")
    assert "results.schema.json" in text, (
        "HOWTO_RUN.md must reference results.schema.json for result validation"
    )


def test_howto_run_covers_condition_a():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "condition a" in text


def test_howto_run_covers_condition_b():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "condition b" in text


def test_howto_run_has_step_structure():
    text = HOWTO.read_text(encoding="utf-8")
    # Must have multiple numbered steps or ## Step sections
    step_headers = [line for line in text.splitlines()
                    if line.startswith("## Step") or line.startswith("## step")]
    numbered = [line for line in text.splitlines()
                if line.strip().startswith("1.") or line.strip().startswith("1 —")]
    assert len(step_headers) >= 4 or len(numbered) >= 4, (
        "HOWTO_RUN.md must have at least 4 numbered steps or ## Step sections"
    )


def test_howto_run_mentions_system_prompt():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "system prompt" in text, (
        "HOWTO_RUN.md must mention recording the system prompt"
    )


def test_howto_run_mentions_evaluator():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "evaluator" in text


def test_howto_run_excludes_automation():
    text = HOWTO.read_text(encoding="utf-8").lower()
    assert "not" in text and ("automat" in text or "solver" in text), (
        "HOWTO_RUN.md must restate that this is not automated execution"
    )


# ---------------------------------------------------------------------------
# run_record_template.json — existence, JSON validity, schema conformance
# ---------------------------------------------------------------------------


def test_run_record_template_exists():
    assert TEMPLATE.exists(), f"run record template must exist at: {TEMPLATE}"


def test_run_record_template_is_valid_json():
    raw = TEMPLATE.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_run_record_template_validates_against_schema():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        assert not errors, (
            "run_record_template.json schema validation failures:\n"
            + "\n".join(f"  {e.message} (path: {list(e.path)})" for e in errors)
        )
    except ImportError:
        for field in ("run_id", "benchmark_scenario", "track",
                      "condition_a_scores", "condition_b_scores"):
            assert field in data, f"template missing field: {field}"


def test_run_record_template_has_sentinel_run_id():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    run_id = data.get("run_id", "")
    assert "00000000" in run_id or "FILL_IN" in run_id.upper(), (
        "run_id in template must use a sentinel value (not a real datetime)"
    )


def test_run_record_template_has_fill_in_model():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert "FILL_IN" in data.get("model", ""), (
        "template 'model' field must be a FILL_IN placeholder"
    )


def test_run_record_template_has_fill_in_provider():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert "FILL_IN" in data.get("provider", ""), (
        "template 'provider' field must be a FILL_IN placeholder"
    )


def test_run_record_template_has_fill_in_evaluator():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert "FILL_IN" in data.get("evaluator", ""), (
        "template 'evaluator' field must be a FILL_IN placeholder"
    )


def test_run_record_template_has_template_warnings():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    warnings = data.get("warnings", [])
    assert len(warnings) >= 1, "template must have at least one warning"
    warning_text = " ".join(warnings).upper()
    assert "TEMPLATE" in warning_text or "FILL_IN" in warning_text or "NOT BEEN FILLED" in warning_text, (
        "template warnings must explicitly state this is an unfilled template"
    )


def test_run_record_template_has_excluded_capabilities():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    caps = data.get("excluded_capabilities", [])
    assert len(caps) >= 3, "template must list at least 3 excluded capabilities"
    text = " ".join(caps).lower()
    assert "mcp" in text or "rag" in text or "solver" in text


def test_run_record_template_has_scenario_paths():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert "sample_bracket" in data.get("package_path", ""), (
        "template package_path must reference the sample bracket scenario"
    )
    assert "sample_bracket" in data.get("raw_source_path", "") or "condition_a" in data.get("raw_source_path", ""), (
        "template raw_source_path must reference the sample bracket scenario"
    )


def test_run_record_template_benchmark_scenario():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert data.get("benchmark_scenario") == "ai_usefulness_v1"


def test_run_record_template_track():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    valid_tracks = {"cad_understanding", "cad_reconstruction", "fem_preprocessing", "cae_deck_understanding"}
    assert data.get("track") in valid_tracks, (
        f"template track must be one of {valid_tracks}"
    )


def test_run_record_template_dimension_scores_present():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    required_dims = [
        "geometry_understanding_score",
        "feature_identification_score",
        "referenceability_score",
        "missingness_honesty_score",
        "hallucination_count",
        "hallucination_penalty",
        "task_success_score",
        "total_score",
    ]
    for condition in ("condition_a_scores", "condition_b_scores"):
        scores = data.get(condition, {})
        for dim in required_dims:
            assert dim in scores, f"template {condition} missing dimension: {dim}"


# ---------------------------------------------------------------------------
# results/README.md — updated for Phase 21B
# ---------------------------------------------------------------------------


def test_results_readme_mentions_template():
    text = (RESULTS_DIR / "README.md").read_text(encoding="utf-8")
    assert "run_record_template.json" in text or "template" in text.lower(), (
        "results/README.md must mention the run record template"
    )


def test_results_readme_mentions_howto():
    text = (RESULTS_DIR / "README.md").read_text(encoding="utf-8")
    assert "HOWTO_RUN.md" in text or "HOWTO" in text, (
        "results/README.md must reference HOWTO_RUN.md"
    )


def test_results_readme_warns_about_single_scenario():
    text = (RESULTS_DIR / "README.md").read_text(encoding="utf-8").lower()
    assert "one run" in text or "not sufficient" in text or "one scenario" in text, (
        "results/README.md must warn about single-scenario limitations"
    )


# ---------------------------------------------------------------------------
# benchmarks/ai_usefulness/README.md — Phase 21B section present
# ---------------------------------------------------------------------------


def test_ai_usefulness_readme_mentions_phase21b():
    text = (BENCHMARK_DIR / "README.md").read_text(encoding="utf-8")
    assert "21B" in text or "HOWTO_RUN" in text or "run_record_template" in text, (
        "benchmarks/ai_usefulness/README.md must reference Phase 21B or HOWTO_RUN.md"
    )


def test_ai_usefulness_readme_links_howto():
    text = (BENCHMARK_DIR / "README.md").read_text(encoding="utf-8")
    assert "HOWTO_RUN.md" in text
