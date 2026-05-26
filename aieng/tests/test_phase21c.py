"""Tests for Phase 21C: per-run directory structure and templates."""
from __future__ import annotations

import json
from pathlib import Path

BENCHMARK_DIR = Path("benchmarks/ai_usefulness")
RUNS_DIR = BENCHMARK_DIR / "results" / "runs"
TEMPLATE_DIR = RUNS_DIR / "run_TEMPLATE"
SCHEMA = BENCHMARK_DIR / "results.schema.json"

# Required template files
COND_A = TEMPLATE_DIR / "condition_a_answers.md"
COND_B = TEMPLATE_DIR / "condition_b_answers.md"
SCORING = TEMPLATE_DIR / "scoring_notes.md"
RESULT = TEMPLATE_DIR / "result.json"
OBS = TEMPLATE_DIR / "observation_report.md"


# ---------------------------------------------------------------------------
# Directory existence
# ---------------------------------------------------------------------------


def test_runs_directory_exists():
    assert RUNS_DIR.exists(), f"runs directory must exist: {RUNS_DIR}"
    assert RUNS_DIR.is_dir()


def test_runs_readme_exists():
    readme = RUNS_DIR / "README.md"
    assert readme.exists(), f"runs/README.md must exist: {readme}"


def test_template_run_directory_exists():
    assert TEMPLATE_DIR.exists(), f"template run directory must exist: {TEMPLATE_DIR}"
    assert TEMPLATE_DIR.is_dir()


# ---------------------------------------------------------------------------
# Required template files exist
# ---------------------------------------------------------------------------


def test_template_condition_a_answers_exists():
    assert COND_A.exists(), f"template condition_a_answers.md must exist: {COND_A}"


def test_template_condition_b_answers_exists():
    assert COND_B.exists(), f"template condition_b_answers.md must exist: {COND_B}"


def test_template_scoring_notes_exists():
    assert SCORING.exists(), f"template scoring_notes.md must exist: {SCORING}"


def test_template_result_json_exists():
    assert RESULT.exists(), f"template result.json must exist: {RESULT}"


def test_template_observation_report_exists():
    assert OBS.exists(), f"template observation_report.md must exist: {OBS}"


# ---------------------------------------------------------------------------
# Placeholder markers — templates must not look like real results
# ---------------------------------------------------------------------------


def test_condition_a_answers_has_fill_in_placeholders():
    text = COND_A.read_text(encoding="utf-8")
    assert "FILL_IN" in text, (
        "condition_a_answers.md must have FILL_IN placeholders to prevent accidental use"
    )


def test_condition_b_answers_has_fill_in_placeholders():
    text = COND_B.read_text(encoding="utf-8")
    assert "FILL_IN" in text, (
        "condition_b_answers.md must have FILL_IN placeholders"
    )


def test_scoring_notes_has_fill_in_placeholders():
    text = SCORING.read_text(encoding="utf-8")
    assert "FILL_IN" in text, (
        "scoring_notes.md must have FILL_IN placeholders"
    )


def test_observation_report_has_fill_in_placeholders():
    text = OBS.read_text(encoding="utf-8")
    assert "FILL_IN" in text, (
        "observation_report.md must have FILL_IN placeholders"
    )


def test_template_result_json_has_fill_in_model():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    assert "FILL_IN" in data.get("model", ""), (
        "template result.json model must be a FILL_IN placeholder, not a real model name"
    )


def test_template_result_json_has_fill_in_provider():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    assert "FILL_IN" in data.get("provider", ""), (
        "template result.json provider must be a FILL_IN placeholder"
    )


def test_template_result_json_has_sentinel_scores():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    # Template must use all-zero sentinel scores — non-zero would look like real data
    for condition in ("condition_a_scores", "condition_b_scores"):
        scores = data.get(condition, {})
        for dim in ("geometry_understanding_score", "feature_identification_score",
                    "referenceability_score", "missingness_honesty_score",
                    "task_success_score", "total_score"):
            assert scores.get(dim) == 0, (
                f"template {condition}.{dim} must be sentinel 0, not a real scored value"
            )


def test_template_result_json_has_sentinel_run_id():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    run_id = data.get("run_id", "")
    assert "00000000" in run_id or "FILL_IN" in run_id.upper(), (
        "template result.json run_id must use a sentinel value, not a real datetime"
    )


# ---------------------------------------------------------------------------
# Template warnings — result.json must have explicit template warnings
# ---------------------------------------------------------------------------


def test_template_result_json_has_template_warning():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    warnings = data.get("warnings", [])
    assert len(warnings) >= 1, "template result.json must have at least one warning"
    combined = " ".join(warnings).upper()
    assert "TEMPLATE" in combined or "NOT BEEN FILLED" in combined or "FILL_IN" in combined, (
        "template result.json warnings must explicitly state this is an unfilled template"
    )


def test_template_result_json_warns_about_single_scenario():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    combined = " ".join(data.get("warnings", [])).lower()
    assert "one run" in combined or "one scenario" in combined or "not sufficient" in combined, (
        "template result.json warnings must include single-scenario limitation note"
    )


# ---------------------------------------------------------------------------
# Schema conformance — template result.json must validate against schema
# ---------------------------------------------------------------------------


def test_template_result_json_is_valid_json():
    raw = RESULT.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_template_result_json_validates_against_schema():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        assert not errors, (
            "run_TEMPLATE/result.json schema validation failures:\n"
            + "\n".join(f"  {e.message} (path: {list(e.path)})" for e in errors)
        )
    except ImportError:
        for field in ("run_id", "benchmark_scenario", "track",
                      "condition_a_scores", "condition_b_scores"):
            data_loaded = json.loads(RESULT.read_text(encoding="utf-8"))
            assert field in data_loaded, f"template result.json missing field: {field}"


def test_template_result_json_benchmark_scenario():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    assert data.get("benchmark_scenario") == "ai_usefulness_v1"


def test_template_result_json_track_is_valid():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    valid = {"cad_understanding", "cad_reconstruction", "fem_preprocessing", "cae_deck_understanding"}
    assert data.get("track") in valid


# ---------------------------------------------------------------------------
# Answer template structure — must have per-question sections
# ---------------------------------------------------------------------------


def test_condition_a_answers_has_q1_through_q5():
    text = COND_A.read_text(encoding="utf-8")
    for qn in ("## Q1", "## Q2", "## Q3", "## Q4", "## Q5"):
        assert qn in text, f"condition_a_answers.md missing question section: {qn}"


def test_condition_b_answers_has_q1_through_q5():
    text = COND_B.read_text(encoding="utf-8")
    for qn in ("## Q1", "## Q2", "## Q3", "## Q4", "## Q5"):
        assert qn in text, f"condition_b_answers.md missing question section: {qn}"


def test_condition_a_answers_has_metadata_section():
    text = COND_A.read_text(encoding="utf-8").lower()
    assert "model" in text and "provider" in text, (
        "condition_a_answers.md must have a metadata section with model and provider fields"
    )


def test_condition_b_answers_has_metadata_section():
    text = COND_B.read_text(encoding="utf-8").lower()
    assert "model" in text and "provider" in text


def test_condition_a_answers_warns_not_real_result():
    text = COND_A.read_text(encoding="utf-8").upper()
    assert "TEMPLATE" in text or "FILL_IN" in text or "PLACEHOLDER" in text, (
        "condition_a_answers.md must prominently mark itself as a template"
    )


def test_condition_b_answers_warns_not_real_result():
    text = COND_B.read_text(encoding="utf-8").upper()
    assert "TEMPLATE" in text or "FILL_IN" in text or "PLACEHOLDER" in text


# ---------------------------------------------------------------------------
# Scoring notes — structure checks
# ---------------------------------------------------------------------------


def test_scoring_notes_has_dimension_summary_table():
    text = SCORING.read_text(encoding="utf-8").lower()
    assert "geometry_understanding" in text or "geometry_understanding_score" in text, (
        "scoring_notes.md must reference scoring dimensions"
    )


def test_scoring_notes_has_hallucination_section():
    text = SCORING.read_text(encoding="utf-8").lower()
    assert "hallucination" in text, (
        "scoring_notes.md must have a hallucination instances section"
    )


def test_scoring_notes_has_delta_section():
    text = SCORING.read_text(encoding="utf-8").lower()
    assert "delta" in text or "b − a" in text or "b - a" in text, (
        "scoring_notes.md must have a delta summary section"
    )


# ---------------------------------------------------------------------------
# Observation report — structure checks
# ---------------------------------------------------------------------------


def test_observation_report_has_limitation_section():
    text = OBS.read_text(encoding="utf-8").lower()
    assert "limitation" in text, (
        "observation_report.md must have a limitations section"
    )


def test_observation_report_warns_no_general_conclusions():
    text = OBS.read_text(encoding="utf-8").lower()
    assert "generalize" in text or "one run" in text or "one scenario" in text or "not sufficient" in text, (
        "observation_report.md must warn against generalizing from one run"
    )


def test_observation_report_has_condition_sections():
    text = OBS.read_text(encoding="utf-8").lower()
    assert "condition a" in text and "condition b" in text, (
        "observation_report.md must have separate Condition A and B sections"
    )


# ---------------------------------------------------------------------------
# runs/README.md — workflow documentation
# ---------------------------------------------------------------------------


def test_runs_readme_explains_copy_step():
    text = (RUNS_DIR / "README.md").read_text(encoding="utf-8").lower()
    assert "copy" in text and "run_template" in text.lower(), (
        "runs/README.md must explain how to copy the template directory"
    )


def test_runs_readme_warns_single_scenario():
    text = (RUNS_DIR / "README.md").read_text(encoding="utf-8").lower()
    assert "one data point" in text or "one run" in text or "not sufficient" in text, (
        "runs/README.md must warn about single-scenario limitation"
    )


def test_runs_readme_lists_required_files():
    text = (RUNS_DIR / "README.md").read_text(encoding="utf-8")
    for fname in ("condition_a_answers.md", "condition_b_answers.md",
                  "scoring_notes.md", "result.json", "observation_report.md"):
        assert fname in text, f"runs/README.md must reference required file: {fname}"


# ---------------------------------------------------------------------------
# HOWTO_RUN.md — updated to reference runs/ directory
# ---------------------------------------------------------------------------


def test_howto_run_references_runs_directory():
    text = (BENCHMARK_DIR / "HOWTO_RUN.md").read_text(encoding="utf-8")
    assert "results/runs" in text or "runs/run_TEMPLATE" in text, (
        "HOWTO_RUN.md must reference the results/runs/ directory structure"
    )


def test_howto_run_mentions_condition_answers_files():
    text = (BENCHMARK_DIR / "HOWTO_RUN.md").read_text(encoding="utf-8")
    assert "condition_a_answers.md" in text or "condition_b_answers.md" in text, (
        "HOWTO_RUN.md must mention the answer files"
    )


# ---------------------------------------------------------------------------
# results/README.md — updated to reference runs/
# ---------------------------------------------------------------------------


def test_results_readme_references_runs_directory():
    text = (BENCHMARK_DIR / "results" / "README.md").read_text(encoding="utf-8")
    assert "runs/" in text or "runs/README.md" in text, (
        "results/README.md must reference the runs/ subdirectory"
    )
