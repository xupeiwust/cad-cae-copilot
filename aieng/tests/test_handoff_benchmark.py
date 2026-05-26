"""Tests for Phase 14D: agent handoff benchmark scaffold."""
from __future__ import annotations

import json
from pathlib import Path

HANDOFF_DIR = Path("benchmarks/handoff")


# ---------------------------------------------------------------------------
# Required files exist
# ---------------------------------------------------------------------------

def test_handoff_benchmark_directory_exists():
    assert HANDOFF_DIR.exists(), "benchmarks/handoff/ directory must exist"
    assert HANDOFF_DIR.is_dir()


def test_handoff_benchmark_required_files_exist():
    required = [
        HANDOFF_DIR / "README.md",
        HANDOFF_DIR / "questions.md",
        HANDOFF_DIR / "scoring_rubric.md",
        HANDOFF_DIR / "expected_observations.md",
        HANDOFF_DIR / "input_index.md",
        HANDOFF_DIR / "result_template.md",
        HANDOFF_DIR / "results.schema.json",
        HANDOFF_DIR / "results" / "README.md",
    ]
    for path in required:
        assert path.exists(), f"missing required handoff benchmark file: {path}"


# ---------------------------------------------------------------------------
# questions.md content
# ---------------------------------------------------------------------------

def test_questions_mention_task_spec():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    assert "task_spec" in text or "task/task_spec.yaml" in text


def test_questions_mention_external_tool_requirements():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    assert "external_tool_requirements" in text or "external tool requirements" in text.lower()


def test_questions_mention_evidence_index():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    assert "evidence_index" in text or "evidence index" in text.lower()



def test_questions_cover_all_ten_groups():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    for section in ("## A.", "## B.", "## C.", "## D.", "## E.",
                    "## F.", "## G.", "## H.", "## I.", "## J."):
        assert section in text, f"missing question group {section!r}"


def test_questions_ask_about_execution_boundary():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    assert "execution boundary" in text.lower() or "aieng_core_executes_external_tools" in text


def test_questions_ask_about_unsupported_claims():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    assert "unsupported" in text


def test_questions_ask_about_writeback():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    assert "writeback" in text.lower() or "write back" in text.lower() or "writeback_requirements" in text


def test_questions_exclude_mcp_rag_and_external_tools():
    text = (HANDOFF_DIR / "questions.md").read_text(encoding="utf-8")
    for phrase in ("MCP tool calls", "RAG", "solver execution", "LLM API calls"):
        assert phrase in text, f"exclusion clause missing: {phrase!r}"


# ---------------------------------------------------------------------------
# scoring_rubric.md content
# ---------------------------------------------------------------------------

def test_rubric_uses_zero_one_two_scale():
    text = (HANDOFF_DIR / "scoring_rubric.md").read_text(encoding="utf-8")
    assert "0 = absent" in text or "0 =" in text
    assert "1 = partially" in text or "1 =" in text
    assert "2 = correct" in text or "2 =" in text


def test_rubric_has_eight_categories():
    text = (HANDOFF_DIR / "scoring_rubric.md").read_text(encoding="utf-8")
    for i in range(1, 9):
        assert f"### Category {i}:" in text, f"missing Category {i} in rubric"


def test_rubric_max_score_is_sixteen():
    text = (HANDOFF_DIR / "scoring_rubric.md").read_text(encoding="utf-8")
    assert "16" in text
    assert "8 categories" in text or "8 × 2" in text or "8 categories × 2" in text


def test_rubric_includes_task_understanding_category():
    text = (HANDOFF_DIR / "scoring_rubric.md").read_text(encoding="utf-8")
    assert "Task understanding" in text or "task understanding" in text.lower()


def test_rubric_includes_execution_boundary_category():
    text = (HANDOFF_DIR / "scoring_rubric.md").read_text(encoding="utf-8")
    assert "execution boundary" in text.lower() or "CAD/CAE execution" in text



def test_rubric_includes_unsupported_claim_refusal_category():
    text = (HANDOFF_DIR / "scoring_rubric.md").read_text(encoding="utf-8")
    assert "Unsupported-claim refusal" in text or "unsupported" in text.lower()



# ---------------------------------------------------------------------------
# expected_observations.md content
# ---------------------------------------------------------------------------

def test_expected_observations_states_cad_cae_side_semantic_export():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "CAD/CAE-side semantic export and evidence package" in text


def test_expected_observations_states_mcp_is_optional():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "MCP" in text
    assert "optional" in text.lower()


def test_expected_observations_states_aieng_does_not_modify_geometry():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    plain = text.replace("**", "")
    assert "does not modify CAD geometry" in plain or "does not directly modify CAD geometry" in plain


def test_expected_observations_states_aieng_does_not_run_solvers():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    plain = text.replace("**", "").lower()
    assert "run solvers" in plain or "run a solver" in plain or "not run solver" in plain


def test_expected_observations_states_aieng_does_not_generate_meshes():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "generate mesh" in text.lower() or "generate meshes" in text.lower()


def test_expected_observations_references_task_spec():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "task/task_spec.yaml" in text


def test_expected_observations_references_external_tool_requirements():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "task/external_tool_requirements.json" in text


def test_expected_observations_references_evidence_index():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "results/evidence_index.json" in text



def test_expected_observations_explains_unsupported_is_not_false():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    plain = text.replace("**", "").lower()
    assert "unsupported" in plain
    assert "not false" in plain or "does not mean the claim is false" in plain


def test_expected_observations_names_what_agent_must_not_say():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "must not" in text.lower() or "must **not**" in text


def test_expected_observations_excludes_mcp_rag_during_benchmark():
    text = (HANDOFF_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "MCP" in text
    assert "RAG" in text


# ---------------------------------------------------------------------------
# results.schema.json content
# ---------------------------------------------------------------------------

def test_results_schema_is_valid_json():
    raw = (HANDOFF_DIR / "results.schema.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_results_schema_has_required_fields():
    data = json.loads((HANDOFF_DIR / "results.schema.json").read_text(encoding="utf-8"))
    required = data.get("required", [])
    for field in ("run_id", "timestamp_utc", "benchmark_scenario", "category_scores",
                  "total_score", "max_score"):
        assert field in required, f"{field!r} must be required in results schema"


def test_results_schema_max_score_const_is_sixteen():
    data = json.loads((HANDOFF_DIR / "results.schema.json").read_text(encoding="utf-8"))
    max_score_prop = data["properties"]["max_score"]
    assert max_score_prop.get("const") == 16


def test_results_schema_benchmark_scenario_const():
    data = json.loads((HANDOFF_DIR / "results.schema.json").read_text(encoding="utf-8"))
    scenario_prop = data["properties"]["benchmark_scenario"]
    assert scenario_prop.get("const") == "agent_handoff_v1"


def test_results_schema_category_score_uses_zero_one_two():
    data = json.loads((HANDOFF_DIR / "results.schema.json").read_text(encoding="utf-8"))
    score_def = data["$defs"]["categoryScore"]["properties"]["score"]
    assert set(score_def.get("enum", [])) == {0, 1, 2}


def test_results_schema_category_names_include_all_eight():
    data = json.loads((HANDOFF_DIR / "results.schema.json").read_text(encoding="utf-8"))
    names_enum = data["$defs"]["categoryScore"]["properties"]["category_name"]["enum"]
    expected = {
        "task_understanding",
        "cad_cae_execution_boundary",
        "protected_region_interface_awareness",
        "evidence_ledger_understanding",
        "claim_map_honesty",
        "external_tool_handoff_plan_usefulness",
        "provenance_and_writeback_awareness",
        "unsupported_claim_refusal",
    }
    assert set(names_enum) == expected


# ---------------------------------------------------------------------------
# README.md content
# ---------------------------------------------------------------------------

def test_handoff_readme_states_purpose():
    text = (HANDOFF_DIR / "README.md").read_text(encoding="utf-8")
    assert "CAD/CAE-side semantic export and evidence package" in text


def test_handoff_readme_excludes_mcp_rag_and_external_tools():
    text = (HANDOFF_DIR / "README.md").read_text(encoding="utf-8")
    lower = text.lower()
    for phrase in ("mcp tool calls", "rag", "solver execution", "llm api calls"):
        assert phrase in lower, f"exclusion clause missing from README: {phrase!r}"


def test_handoff_readme_lists_eight_categories():
    text = (HANDOFF_DIR / "README.md").read_text(encoding="utf-8")
    assert "8 categories" in text or "eight categories" in text.lower()


def test_handoff_readme_links_to_all_required_files():
    text = (HANDOFF_DIR / "README.md").read_text(encoding="utf-8")
    for link in ("questions.md", "scoring_rubric.md", "expected_observations.md",
                 "input_index.md", "result_template.md", "results.schema.json"):
        assert link in text, f"README missing link to {link!r}"


# ---------------------------------------------------------------------------
# benchmarks/README.md mentions handoff benchmark
# ---------------------------------------------------------------------------

def test_benchmarks_readme_mentions_handoff_benchmark():
    text = Path("benchmarks/README.md").read_text(encoding="utf-8")
    assert "handoff" in text.lower()
    assert "handoff/README.md" in text or "handoff/" in text
