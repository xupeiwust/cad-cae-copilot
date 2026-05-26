from __future__ import annotations

from pathlib import Path

BENCHMARK_DIR = Path("benchmark_runs/bracket_001_manual")


def test_benchmark_run_directory_exists():
    assert BENCHMARK_DIR.is_dir()


def test_required_files_exist():
    for name in [
        "instructions.md",
        "questions.md",
        "raw_step_input.md",
        "aieng_input_index.md",
        "scoring_sheet.md",
        "expected_observations.md",
    ]:
        assert (BENCHMARK_DIR / name).exists(), f"missing {name}"


def test_scoring_sheet_has_raw_step_and_aieng_columns():
    text = (BENCHMARK_DIR / "scoring_sheet.md").read_text(encoding="utf-8")
    assert "Raw STEP" in text or "raw STEP" in text or "Condition A" in text
    assert ".aieng" in text or "Condition B" in text


def test_aieng_input_index_lists_readme_for_ai_and_feature_graph():
    text = (BENCHMARK_DIR / "aieng_input_index.md").read_text(encoding="utf-8")
    assert "README_FOR_AI.md" in text
    assert "feature_graph.json" in text


def test_raw_step_input_excludes_aieng_files():
    text = (BENCHMARK_DIR / "raw_step_input.md").read_text(encoding="utf-8")
    assert "README_FOR_AI.md" in text
    assert "feature_graph.json" in text
    assert "not" in text.lower() or "do not" in text.lower() or "NOT" in text


def test_raw_step_input_says_not_to_include_aieng_resources():
    text = (BENCHMARK_DIR / "raw_step_input.md").read_text(encoding="utf-8")
    assert "Do not" in text or "do not" in text or "NOT" in text
    assert "README_FOR_AI.md" in text
    assert "constraints.json" in text or "setup.yaml" in text


def test_instructions_reference_both_conditions():
    text = (BENCHMARK_DIR / "instructions.md").read_text(encoding="utf-8")
    assert "Condition A" in text
    assert "Condition B" in text
    assert "RAG" in text
    assert "MCP" in text


def test_instructions_reference_demo_script():
    text = (BENCHMARK_DIR / "instructions.md").read_text(encoding="utf-8")
    assert "run_reference_demo.py" in text or "aieng import-step" in text


def test_expected_observations_describes_raw_step_limitations():
    text = (BENCHMARK_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "vague" in text.lower() or "cannot" in text.lower()
    assert "feat_hole_pattern_001" in text or "protected" in text.lower()
    assert "candidate" in text.lower()
    assert "solver" in text.lower()


def test_benchmarks_readme_links_to_manual_run():
    text = Path("benchmarks/README.md").read_text(encoding="utf-8")
    assert "bracket_001_manual" in text


def test_results_run_001_exists():
    assert (BENCHMARK_DIR / "results_run_001.md").exists()


def test_scoring_rubric_has_honesty_dimension():
    text = Path("benchmarks/scoring_rubric.md").read_text(encoding="utf-8")
    assert "Honesty" in text or "honesty" in text
    assert "non-hallucination" in text or "hallucination" in text


def test_scoring_rubric_has_usefulness_dimension():
    text = Path("benchmarks/scoring_rubric.md").read_text(encoding="utf-8")
    assert "Usefulness" in text or "usefulness" in text
    assert "actionable" in text or "Actionable" in text


def test_scoring_sheet_has_honesty_and_usefulness_columns():
    text = (BENCHMARK_DIR / "scoring_sheet.md").read_text(encoding="utf-8")
    assert "Honesty" in text or "honesty" in text
    assert "Usefulness" in text or "usefulness" in text


def test_benchmarks_readme_links_to_results_run_001():
    text = Path("benchmarks/README.md").read_text(encoding="utf-8")
    assert "results_run_001.md" in text


def test_results_run_001_records_key_conclusion():
    text = (BENCHMARK_DIR / "results_run_001.md").read_text(encoding="utf-8")
    assert "honest" in text.lower()
    assert "actionable" in text.lower()


def test_results_run_001_includes_score_table():
    text = (BENCHMARK_DIR / "results_run_001.md").read_text(encoding="utf-8")
    assert "Honesty" in text
    assert "Usefulness" in text
    assert "Condition A" in text
    assert "Condition B" in text


def test_aieng_input_index_includes_solver_deck():
    text = (BENCHMARK_DIR / "aieng_input_index.md").read_text(encoding="utf-8")
    assert "simulation/solver_deck.inp" in text


def test_aieng_input_index_includes_validation_status():
    text = (BENCHMARK_DIR / "aieng_input_index.md").read_text(encoding="utf-8")
    assert "validation/status.yaml" in text


def test_aieng_input_index_includes_phase10_cae_mapping_files():
    text = (BENCHMARK_DIR / "aieng_input_index.md").read_text(encoding="utf-8")
    assert "simulation/cae_mapping.json" in text
    assert "simulation/cae_imports/parsed_boundary_conditions.json" in text
    assert "simulation/cae_imports/parsed_loads.json" in text
    assert "objects/interface_graph.json" in text
    assert "objects/object_registry.json" in text


def test_instructions_mention_update_validation_status():
    text = (BENCHMARK_DIR / "instructions.md").read_text(encoding="utf-8")
    assert "update-validation-status" in text


def test_instructions_mention_export_calculix():
    text = (BENCHMARK_DIR / "instructions.md").read_text(encoding="utf-8")
    assert "export-calculix" in text


def test_instructions_include_phase10c_cae_demo_order():
    text = (BENCHMARK_DIR / "instructions.md").read_text(encoding="utf-8")
    apply_pos = text.index("aieng apply-cae-mapping")
    first_interface_pos = text.index("aieng build-interface-graph")
    second_interface_pos = text.index("aieng build-interface-graph", first_interface_pos + 1)
    registry_pos = text.index("aieng build-object-registry")
    assert "aieng import-cae-deck" in text
    assert first_interface_pos < apply_pos < second_interface_pos < registry_pos


def test_expected_observations_mention_solver_deck_scaffold():
    text = (BENCHMARK_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "scaffold" in text.lower()
    assert "solver_deck.inp" in text or "solver deck" in text.lower()


def test_expected_observations_mention_no_solver_run():
    text = (BENCHMARK_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "no solver has been run" in text.lower() or "solver has been run" in text.lower()


def test_expected_observations_mention_phase10_user_mapping_and_no_solver_run():
    text = (BENCHMARK_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "user-provided" in text
    assert "FIXED_HOLES" in text
    assert "LOAD_FACE" in text
    assert "simulation/cae_mapping.json" in text
    assert "objects/interface_graph.json" in text
    assert "should not claim" in text.lower()
    assert "solver" in text.lower()


def test_expected_observations_mention_validation_status_claim_policy():
    text = (BENCHMARK_DIR / "expected_observations.md").read_text(encoding="utf-8")
    assert "validation/status.yaml" in text
    assert "claim_policy" in text or "forbidden_claims" in text


def test_results_run_002_exists():
    assert (BENCHMARK_DIR / "results_run_002.md").exists()


def test_results_run_002_mentions_validation_status():
    text = (BENCHMARK_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "validation/status.yaml" in text


def test_results_run_002_mentions_solver_deck():
    text = (BENCHMARK_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "simulation/solver_deck.inp" in text or "solver_deck.inp" in text


def test_results_run_002_mentions_scaffold():
    text = (BENCHMARK_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "scaffold" in text.lower()


def test_results_run_002_mentions_forbidden_claims():
    text = (BENCHMARK_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "forbidden_claims" in text or "forbidden claims" in text.lower()


def test_results_run_002_mentions_no_solver_run():
    text = (BENCHMARK_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "solver" in text.lower() and "not_run" in text or "no solver has been run" in text.lower()


def test_benchmarks_readme_links_to_results_run_002():
    text = Path("benchmarks/README.md").read_text(encoding="utf-8")
    assert "results_run_002.md" in text


# Tests for real_bracket_001 benchmark runs (Phase 11D)

REAL_BRACKET_DIR = Path("benchmark_runs/real_bracket_001")


def test_real_bracket_directory_exists():
    assert REAL_BRACKET_DIR.is_dir()


def test_real_bracket_readme_exists():
    assert (REAL_BRACKET_DIR / "README.md").exists()


def test_real_bracket_readme_mentions_both_runs():
    text = (REAL_BRACKET_DIR / "README.md").read_text(encoding="utf-8")
    assert "results_run_001.md" in text
    assert "results_run_002.md" in text


def test_real_bracket_results_run_001_exists():
    assert (REAL_BRACKET_DIR / "results_run_001.md").exists()


def test_real_bracket_results_run_002_exists():
    assert (REAL_BRACKET_DIR / "results_run_002.md").exists()


def test_real_bracket_results_run_002_mentions_optional_backend_available():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "optional" in text.lower() or "available" in text.lower()
    assert "CadQuery" in text or "OCP" in text or "cadquery" in text


def test_real_bracket_results_run_002_mentions_validation_passed():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "validation" in text.lower() and "pass" in text.lower()


def test_real_bracket_results_run_002_mentions_topology_extraction():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "topology" in text.lower() or "topology_map" in text


def test_real_bracket_results_run_002_mentions_aag():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "aag" in text.lower() or "attributed adjacency graph" in text.lower()


def test_real_bracket_results_run_002_mentions_no_mesh():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "no mesh" in text.lower() or "mesh was not generated" in text.lower() or "without mesh" in text.lower()


def test_real_bracket_results_run_002_mentions_no_solver():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "no solver" in text.lower() or "solver was not" in text.lower() or "solver run" in text.lower()


def test_real_bracket_results_run_002_mentions_no_geometry_modification():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "no geometry" in text.lower() or "geometry was not modified" in text.lower() or "geometry modification" in text.lower()


def test_real_bracket_results_run_002_mentions_conservative_policy():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "conservative" in text.lower() or "claim policy" in text.lower()


def test_real_bracket_results_run_002_lists_generated_resources():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    for resource in [
        "manifest.json",
        "geometry/topology_map.json",
        "graph/aag.json",
        "graph/feature_graph.json",
        "graph/constraints.json",
        "ai/summary.md",
        "validation/status.yaml",
    ]:
        assert resource in text, f"missing resource: {resource}"


def test_real_bracket_results_run_002_references_run_001():
    text = (REAL_BRACKET_DIR / "results_run_002.md").read_text(encoding="utf-8")
    assert "Run 001" in text or "run_001" in text or "results_run_001" in text


def test_real_bracket_results_run_001_documents_backend_status():
    text = (REAL_BRACKET_DIR / "results_run_001.md").read_text(encoding="utf-8")
    assert ("available" in text.lower() or "backend" in text.lower())


def test_real_bracket_results_ai_run_001_exists():
    assert (REAL_BRACKET_DIR / "results_ai_run_001.md").exists()


def test_real_bracket_results_ai_run_001_has_required_totals():
    text = (REAL_BRACKET_DIR / "results_ai_run_001.md").read_text(encoding="utf-8")
    assert "| A Raw STEP | 18 | 8 | 18 |" in text
    assert "| B .aieng | 18 | 18 | 18 |" in text


def test_real_bracket_results_ai_run_001_mentions_real_demo_completion_and_validation():
    text = (REAL_BRACKET_DIR / "results_ai_run_001.md").read_text(encoding="utf-8")
    assert "Real STEP AI Benchmark Run 001" in text
    assert "Real demo completed" in text
    assert "Package validation passed" in text


def test_real_bracket_results_ai_run_001_mentions_no_mesh_no_solver_no_geometry_modification():
    text = (REAL_BRACKET_DIR / "results_ai_run_001.md").read_text(encoding="utf-8")
    assert "No mesh" in text
    assert "No external solver" in text or "No solver" in text
    assert "No geometry modification" in text


def test_real_bracket_results_ai_run_001_mentions_no_engineering_safety_claim_and_no_external_scoring_claims():
    text = (REAL_BRACKET_DIR / "results_ai_run_001.md").read_text(encoding="utf-8")
    assert "No engineering safety claim" in text
    assert "Manual scoring" in text


def test_real_bracket_results_ai_run_001_mentions_semantic_task_understanding_layer_for_cax_process_chains():
    text = (REAL_BRACKET_DIR / "results_ai_run_001.md").read_text(encoding="utf-8")
    assert "semantic task-understanding layer" in text
    assert "CAX process chains" in text
