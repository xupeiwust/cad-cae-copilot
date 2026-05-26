"""Tests for Phase 21A: sample_bracket_cad_understanding benchmark scenario."""
from __future__ import annotations

import json
from pathlib import Path

SCENARIO_DIR = Path(
    "benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding"
)
SCHEMA_FILE = Path("benchmarks/ai_usefulness/results.schema.json")


# ---------------------------------------------------------------------------
# Directory and required files
# ---------------------------------------------------------------------------


def test_scenario_directory_exists():
    assert SCENARIO_DIR.exists(), f"scenario directory missing: {SCENARIO_DIR}"
    assert SCENARIO_DIR.is_dir()


def test_scenario_required_files_exist():
    required = [
        SCENARIO_DIR / "README.md",
        SCENARIO_DIR / "condition_a.md",
        SCENARIO_DIR / "condition_b_index.md",
        SCENARIO_DIR / "questions.md",
        SCENARIO_DIR / "expected_scoring.md",
        SCENARIO_DIR / "example_result.json",
    ]
    for path in required:
        assert path.exists(), f"required scenario file missing: {path}"


# ---------------------------------------------------------------------------
# example_result.json — schema and field checks
# ---------------------------------------------------------------------------


def test_example_result_is_valid_json():
    raw = (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_example_result_benchmark_scenario_field():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    assert data.get("benchmark_scenario") == "ai_usefulness_v1"


def test_example_result_track_is_cad_understanding():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    assert data.get("track") == "cad_understanding"


def test_example_result_run_id_format():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    import re
    assert re.match(r"^run_[0-9]{8}T[0-9]{6}Z$", data.get("run_id", "")), (
        "run_id must match run_YYYYMMDDTHHMMSSZ"
    )


def test_example_result_has_both_condition_scores():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    assert "condition_a_scores" in data
    assert "condition_b_scores" in data


def test_example_result_condition_a_required_dimensions():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
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
    scores = data["condition_a_scores"]
    for dim in required_dims:
        assert dim in scores, f"condition_a_scores missing dimension: {dim}"


def test_example_result_condition_b_required_dimensions():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
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
    scores = data["condition_b_scores"]
    for dim in required_dims:
        assert dim in scores, f"condition_b_scores missing dimension: {dim}"


def test_example_result_condition_b_scores_exceed_condition_a():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    a_total = data["condition_a_scores"]["total_score"]
    b_total = data["condition_b_scores"]["total_score"]
    assert b_total > a_total, (
        f"Condition B total ({b_total}) must exceed Condition A total ({a_total})"
    )


def test_example_result_hallucination_penalty_consistent():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    for condition in ("condition_a_scores", "condition_b_scores"):
        scores = data[condition]
        count = scores["hallucination_count"]
        penalty = scores["hallucination_penalty"]
        assert penalty == -count, (
            f"{condition}: hallucination_penalty ({penalty}) must equal -hallucination_count ({count})"
        )


def test_example_result_validates_against_schema():
    data = json.loads(
        (SCENARIO_DIR / "example_result.json").read_text(encoding="utf-8")
    )
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        assert not errors, (
            f"example_result.json schema validation failures:\n"
            + "\n".join(f"  {e.message} (path: {list(e.path)})" for e in errors)
        )
    except ImportError:
        # Manual field check when jsonschema not installed
        for field in ("run_id", "timestamp_utc", "benchmark_scenario", "track",
                      "condition_a_scores", "condition_b_scores"):
            assert field in data, f"example_result.json missing field: {field}"


# ---------------------------------------------------------------------------
# questions.md content
# ---------------------------------------------------------------------------


def test_questions_mentions_track_a():
    text = (SCENARIO_DIR / "questions.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "track" in lower or "q1" in lower


def test_questions_lists_excluded_mcp():
    text = (SCENARIO_DIR / "questions.md").read_text(encoding="utf-8")
    assert "MCP" in text or "mcp" in text.lower()


def test_questions_lists_excluded_rag():
    text = (SCENARIO_DIR / "questions.md").read_text(encoding="utf-8")
    assert "RAG" in text or "retrieval" in text.lower()


def test_questions_lists_excluded_solver():
    text = (SCENARIO_DIR / "questions.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "solver" in lower or "solver execution" in lower


def test_questions_lists_excluded_llm_api_calls():
    text = (SCENARIO_DIR / "questions.md").read_text(encoding="utf-8")
    assert "LLM API calls" in text or "llm api" in text.lower()


def test_questions_has_five_questions():
    text = (SCENARIO_DIR / "questions.md").read_text(encoding="utf-8")
    # At least Q1–Q5 headers present
    for qn in ("## Q1", "## Q2", "## Q3", "## Q4", "## Q5"):
        assert qn in text, f"questions.md missing question header: {qn}"


# ---------------------------------------------------------------------------
# condition_a.md content
# ---------------------------------------------------------------------------


def test_condition_a_is_substantial():
    text = (SCENARIO_DIR / "condition_a.md").read_text(encoding="utf-8")
    assert len(text) > 500, "condition_a.md appears too short to be a realistic source input"


def test_condition_a_contains_document_xml():
    text = (SCENARIO_DIR / "condition_a.md").read_text(encoding="utf-8")
    assert "Document" in text or "Object" in text, (
        "condition_a.md should contain Document.xml-derived content"
    )


def test_condition_a_names_model_objects():
    text = (SCENARIO_DIR / "condition_a.md").read_text(encoding="utf-8")
    assert "Plate" in text or "MountingHole" in text or "Flange" in text, (
        "condition_a.md should reference named model objects"
    )


# ---------------------------------------------------------------------------
# condition_b_index.md content
# ---------------------------------------------------------------------------


def test_condition_b_index_has_backtick_resources():
    text = (SCENARIO_DIR / "condition_b_index.md").read_text(encoding="utf-8")
    assert "`" in text, "condition_b_index.md must list at least one resource in backticks"


def test_condition_b_index_lists_feature_graph():
    text = (SCENARIO_DIR / "condition_b_index.md").read_text(encoding="utf-8")
    assert "feature_graph.json" in text


def test_condition_b_index_lists_object_registry():
    text = (SCENARIO_DIR / "condition_b_index.md").read_text(encoding="utf-8")
    assert "object_registry.json" in text


def test_condition_b_index_lists_conversion_manifest():
    text = (SCENARIO_DIR / "condition_b_index.md").read_text(encoding="utf-8")
    assert "conversion_manifest.json" in text


# ---------------------------------------------------------------------------
# expected_scoring.md content
# ---------------------------------------------------------------------------


def test_expected_scoring_covers_geometry_dimension():
    text = (SCENARIO_DIR / "expected_scoring.md").read_text(encoding="utf-8")
    assert "geometry_understanding" in text or "geometry_understanding_score" in text


def test_expected_scoring_covers_feature_identification():
    text = (SCENARIO_DIR / "expected_scoring.md").read_text(encoding="utf-8")
    assert "feature_identification" in text


def test_expected_scoring_covers_referenceability():
    text = (SCENARIO_DIR / "expected_scoring.md").read_text(encoding="utf-8")
    assert "referenceability" in text


def test_expected_scoring_covers_missingness_honesty():
    text = (SCENARIO_DIR / "expected_scoring.md").read_text(encoding="utf-8")
    assert "missingness_honesty" in text


def test_expected_scoring_explains_condition_a_and_b():
    text = (SCENARIO_DIR / "expected_scoring.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "condition a" in lower
    assert "condition b" in lower


def test_expected_scoring_shows_illustrative_delta():
    text = (SCENARIO_DIR / "expected_scoring.md").read_text(encoding="utf-8")
    # Delta mentioned in scoring table or narrative
    assert "delta" in text.lower() or "Δ" in text


# ---------------------------------------------------------------------------
# README.md content
# ---------------------------------------------------------------------------


def test_scenario_readme_describes_model():
    text = (SCENARIO_DIR / "README.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "bracket" in lower or "plate" in lower or "mounting" in lower


def test_scenario_readme_references_both_conditions():
    text = (SCENARIO_DIR / "README.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "condition a" in lower or "condition_a" in lower
    assert "condition b" in lower or "condition_b" in lower


# ---------------------------------------------------------------------------
# benchmarks/ai_usefulness/README.md mentions scenario
# ---------------------------------------------------------------------------


def test_ai_usefulness_readme_mentions_scenarios():
    text = Path("benchmarks/ai_usefulness/README.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "scenario" in lower or "scenarios/" in lower
