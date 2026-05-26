from __future__ import annotations

from pathlib import Path


def test_benchmark_files_exist():
    for path in [
        Path("benchmarks/README.md"),
        Path("benchmarks/questions.md"),
        Path("benchmarks/raw_step_expected_limitations.md"),
        Path("benchmarks/aieng_expected_capabilities.md"),
        Path("benchmarks/scoring_rubric.md"),
        Path("benchmarks/run_manual_benchmark.md"),
        Path("benchmarks/results.schema.json"),
        Path("benchmarks/results/README.md"),
    ]:
        assert path.exists(), f"missing benchmark file: {path}"


def test_benchmark_readme_excludes_external_augmentation():
    text = Path("benchmarks/README.md").read_text(encoding="utf-8")
    for phrase in ["RAG", "MCP tools", "skills", "plugins", "LLM fine-tuning"]:
        assert phrase in text
    assert "raw STEP/B-rep" in text
    assert "`.aieng` package" in text


def test_scoring_rubric_contains_zero_one_two_scale():
    text = Path("benchmarks/scoring_rubric.md").read_text(encoding="utf-8")
    assert "0 = absent or incorrect" in text
    assert "1 = partially correct but vague" in text
    assert "2 = correct, grounded" in text


def test_questions_include_validation_state_and_protected_regions():
    text = Path("benchmarks/questions.md").read_text(encoding="utf-8")
    assert "## C. Constraints and protected regions" in text
    assert "Which features should not be modified?" in text
    assert "## E. Validation state" in text
    assert "Has a solver run?" in text
    assert "Is there evidence that the design is safe?" in text


def test_questions_include_cae_import_and_mapping_questions():
    text = Path("benchmarks/questions.md").read_text(encoding="utf-8")
    assert "## H. CAE import and mapping" in text
    assert "FIXED_HOLES" in text
    assert "LOAD_FACE" in text
    assert "Does imported CAE setup prove a solver was run?" in text


def test_benchmark_results_readme_describes_json_schema_and_restrictions():
    text = Path("benchmarks/results/README.md").read_text(encoding="utf-8")
    assert "run_<timestamp>.json" in text
    assert "16" in text
    assert "8" in text
    assert "category" in text.lower()
    assert "RAG" in text
    assert "MCP" in text


def test_benchmark_results_directory_contains_recorded_run():
    results = sorted(Path("benchmarks/results").glob("run_*.json"))
    assert results, "expected at least one recorded benchmark result"
