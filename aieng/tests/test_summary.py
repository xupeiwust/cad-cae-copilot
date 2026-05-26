from __future__ import annotations

import json
import zipfile

import yaml

from aieng.ai.summary_writer import AI_SUMMARY_PATH, README_FOR_AI_PATH, summarize_package
from aieng.cli import main
from aieng.context.apply_context import apply_context_package
from aieng.geometry.step_importer import import_step_package
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.feature_graph import recognize_features_package
from aieng.package import read_manifest
from aieng.validate import validate_package

FAKE_STEP_CONTENT = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

VALID_CONTEXT = {
    "material": "Al6061-T6",
    "protected_features": ["feat_hole_pattern_001"],
    "simulation": {
        "type": "static_structural",
        "fixed": ["feat_hole_pattern_001"],
        "loads": [
            {"target": "feat_base_plate_001", "type": "force", "value_n": 500, "direction": [1, 0, 0]}
        ],
    },
    "targets": {"max_von_mises_stress_mpa": 120},
    "assumptions": [
        "Mounting hole pattern is treated as fixed support.",
        "Load target is provided by user context.",
    ],
}


def write_fake_step(path):
    path.write_bytes(FAKE_STEP_CONTENT)
    return path


def write_context(path):
    path.write_text(yaml.safe_dump(VALID_CONTEXT, sort_keys=False), encoding="utf-8")
    return path


def phase4_package(tmp_path):
    step_path = write_fake_step(tmp_path / "bracket.step")
    package_path = tmp_path / "bracket_001.aieng"
    context_path = write_context(tmp_path / "context.yaml")
    import_step_package(step_path, package_path)
    extract_topology_package(package_path)
    recognize_features_package(package_path)
    apply_context_package(package_path, context_path)
    return package_path


def read_member_text(package_path, member):
    with zipfile.ZipFile(package_path) as package:
        return package.read(member).decode("utf-8")


def test_summarize_happy_path_after_apply_context(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    readme = read_member_text(package_path, README_FOR_AI_PATH)
    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "# .aieng AI Reader Guide: bracket_001" in readme
    assert "# Engineering Summary" in summary


def test_summarize_fails_if_package_does_not_exist(tmp_path):
    try:
        summarize_package(tmp_path / "missing.aieng")
    except FileNotFoundError as exc:
        assert "package does not exist" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_summarize_writes_readme_for_ai(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    with zipfile.ZipFile(package_path) as package:
        assert README_FOR_AI_PATH in set(package.namelist())


def test_summarize_writes_ai_summary(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    with zipfile.ZipFile(package_path) as package:
        assert AI_SUMMARY_PATH in set(package.namelist())


def test_summarize_manifest_references_both_summary_files(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    manifest = read_manifest(package_path)
    assert manifest["resources"]["readme_for_ai"] == README_FOR_AI_PATH
    assert manifest["resources"]["ai"]["summary"] == AI_SUMMARY_PATH


def test_readme_for_ai_includes_guiding_ai_reader_rules(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "## Rules for AI readers" in readme
    assert "Do not claim the design is safe unless solver-validated evidence exists." in readme
    assert "Do not treat candidate features as confirmed engineering truth." in readme
    assert "Do not modify protected regions." in readme
    assert "Do not invent material properties." in readme
    assert "Distinguish extracted facts, inferred candidates, user-provided context, and validated results." in readme
    assert "Use object IDs when referring to features, topology entities, constraints, or protected regions." in readme


def test_readme_for_ai_says_structured_resources_are_source_of_truth(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "Structured JSON/YAML resources are the source of truth." in readme


def test_ai_summary_includes_feature_ids(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "feat_base_plate_001" in summary
    assert "feat_hole_pattern_001" in summary


def test_ai_summary_includes_feature_recognition_quality_section(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "## Feature recognition quality" in summary
    assert "confidence_counts:" in summary
    assert "features_with_explicit_uncertainty_notes:" in summary


def test_readme_includes_feature_recognition_quality_section(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "## Feature recognition quality" in readme
    assert "Recognition output is candidate-level" in readme


def test_ai_summary_includes_protected_feature_ids(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "## Protected regions" in summary
    assert "feat_hole_pattern_001" in summary
    assert "delete" in summary


def test_ai_summary_includes_material_and_simulation_setup(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "Al6061-T6" in summary
    assert "youngs_modulus_mpa" in summary
    assert "sim_static_001" in summary
    assert "static_structural" in summary
    assert "feat_base_plate_001" in summary


def test_ai_summary_states_no_solver_result_attached(tmp_path):
    package_path = phase4_package(tmp_path)

    summarize_package(package_path)

    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "No solver result has been attached." in summary
    assert "No stress/displacement claim is validated." in summary


def test_summarize_does_not_overwrite_by_default(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    with zipfile.ZipFile(package_path) as package:
        original = package.read(README_FOR_AI_PATH)

    try:
        summarize_package(package_path)
    except FileExistsError as exc:
        assert "use --overwrite" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")

    with zipfile.ZipFile(package_path) as package:
        assert package.read(README_FOR_AI_PATH) == original


def test_summarize_overwrites_with_overwrite(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)

    summarize_package(package_path, overwrite=True)

    assert "README_FOR_AI.md" in read_member_text(package_path, README_FOR_AI_PATH)


def test_cli_summarize_happy_path_and_validate(tmp_path, capsys):
    package_path = phase4_package(tmp_path)

    assert main(["summarize", str(package_path)]) == 0
    output = capsys.readouterr().out
    assert "PASS generated AI-readable summaries" in output
    assert "PASS README_FOR_AI.md written" in output
    assert "PASS ai/summary.md written" in output

    assert main(["validate", str(package_path)]) == 0
    validate_output = capsys.readouterr().out
    assert "PASS README_FOR_AI.md exists" in validate_output
    assert "PASS ai/summary.md exists" in validate_output
    assert "PASS README_FOR_AI.md is non-empty text" in validate_output
    assert "PASS ai/summary.md is non-empty text" in validate_output


def test_cli_summarize_does_not_overwrite_by_default(tmp_path, capsys):
    package_path = phase4_package(tmp_path)
    assert main(["summarize", str(package_path)]) == 0
    capsys.readouterr()

    assert main(["summarize", str(package_path)]) == 2
    captured = capsys.readouterr()
    assert "FAIL summary resources already exist" in captured.err


def test_validate_passes_after_summarize(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)

    report = validate_package(package_path)
    rendered = report.render()

    assert report.ok
    assert "PASS README_FOR_AI.md is non-empty text" in rendered
    assert "PASS ai/summary.md is non-empty text" in rendered


def test_summaries_are_derived_and_not_source_of_truth(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)

    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    readme = read_member_text(package_path, README_FOR_AI_PATH)

    assert "derived summary" in summary
    assert "derived summaries" in readme


def test_summary_files_are_non_empty_text_when_manifest_references_them(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)

    with zipfile.ZipFile(package_path) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["resources"]["readme_for_ai"] == README_FOR_AI_PATH
        assert package.read(README_FOR_AI_PATH).decode("utf-8").strip()
        assert package.read(AI_SUMMARY_PATH).decode("utf-8").strip()


# ---------------------------------------------------------------------------
# AI entrypoint hardening tests (reading order + validity gate)
# ---------------------------------------------------------------------------

def test_readme_for_ai_contains_required_reading_order_section(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "## Required Reading Order for AI Readers" in readme


def test_readme_for_ai_mentions_validation_status_yaml(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "validation/status.yaml" in readme


def test_readme_for_ai_mentions_solver_deck_inp(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "simulation/solver_deck.inp" in readme


def test_readme_for_ai_mentions_patches_glob(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "ai/patches/*.json" in readme


def test_readme_for_ai_includes_before_answering_section(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "## Before Answering Engineering Validity Questions" in readme


def test_readme_for_ai_reading_order_lists_validation_before_feature_graph(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    idx_validation = readme.index("validation/status.yaml")
    idx_feature = readme.index("graph/feature_graph.json")
    assert idx_validation < idx_feature, "validation/status.yaml should appear before graph/feature_graph.json in reading order"


def test_readme_for_ai_claim_discipline_rules_present(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "solver_execution" in readme
    assert "not_run" in readme
    assert "stress_validation" in readme
    assert "not_validated" in readme


def test_ai_summary_points_to_validation_status_when_present(tmp_path):
    from aieng.validation.status_writer import update_validation_status_package
    package_path = phase4_package(tmp_path)
    update_validation_status_package(package_path)
    summarize_package(package_path)
    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "validation/status.yaml" in summary


def test_ai_summary_does_not_mention_validation_status_when_absent(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    # Only appears in the conditional line; if status is absent the line should not be emitted
    assert "validation/status.yaml" not in summary


def test_summary_includes_task_spec_section_when_present(tmp_path):
    from aieng.task.task_spec_writer import write_task_spec_package
    package_path = phase4_package(tmp_path)
    write_task_spec_package(package_path, "Reduce mass by 15%.", task_id="task_001")
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    summary = read_member_text(package_path, AI_SUMMARY_PATH)
    assert "## Active task contract" in readme
    assert "task_id: `task_001`" in readme
    assert "intent: Reduce mass by 15%." in readme
    assert "mode: `proposal_only`" in readme
    assert "## Active task contract" in summary
    assert "task_id: `task_001`" in summary


def test_summary_shows_absent_task_spec_message_when_missing(tmp_path):
    package_path = phase4_package(tmp_path)
    summarize_package(package_path)
    readme = read_member_text(package_path, README_FOR_AI_PATH)
    assert "## Active task contract" in readme
    assert "task/task_spec.yaml` is absent" in readme


# ---------------------------------------------------------------------------
# Phase 15D: enhanced evidence/claim/trace summary visibility
# ---------------------------------------------------------------------------

def _make_package_with_evidence(tmp_path):
    from aieng.package import create_package
    from aieng.task.task_spec_writer import write_task_spec_package
    from aieng.task.external_tool_requirements_writer import write_external_tool_requirements_package
    from aieng.results.evidence_writer import write_evidence_scaffold_package, record_evidence_package
    from aieng.provenance.tool_trace_writer import record_trace_package

    pkg = tmp_path / "test.aieng"
    create_package("test_model", pkg)
    write_task_spec_package(pkg, "Reduce mass by 15%.", task_id="task_001")
    write_external_tool_requirements_package(pkg, handoff_id="handoff_001")
    write_evidence_scaffold_package(pkg)
    return pkg


def _summarize_and_read(pkg):
    summarize_package(pkg, overwrite=True)
    readme = read_member_text(pkg, README_FOR_AI_PATH)
    summary = read_member_text(pkg, AI_SUMMARY_PATH)
    return readme, summary


# Evidence index: breakdown by type and producer kind

def test_summary_evidence_breakdown_by_type(tmp_path):
    from aieng.results.evidence_writer import record_evidence_package
    pkg = _make_package_with_evidence(tmp_path)
    record_evidence_package(
        pkg,
        evidence_id="ev_solver_001",
        evidence_type="solver_result",
        producer_kind="external_solver",
        producer_tool="freecad",
        artifact_kind="result_file",
        artifact_path="results/out.vtk",
        claim_support=["claim_solver_result_001"],
    )
    readme, summary = _summarize_and_read(pkg)
    assert "solver_result" in summary
    assert "solver_result" in readme


def test_summary_evidence_breakdown_by_producer_kind(tmp_path):
    from aieng.results.evidence_writer import record_evidence_package
    pkg = _make_package_with_evidence(tmp_path)
    record_evidence_package(
        pkg,
        evidence_id="ev_solver_001",
        evidence_type="solver_result",
        producer_kind="external_solver",
        producer_tool="freecad",
        artifact_kind="result_file",
        artifact_path="results/out.vtk",
        claim_support=["claim_solver_result_001"],
    )
    readme, summary = _summarize_and_read(pkg)
    assert "external_solver" in summary
    assert "external_solver" in readme


def test_summary_evidence_verification_status_breakdown(tmp_path):
    pkg = _make_package_with_evidence(tmp_path)
    readme, summary = _summarize_and_read(pkg)
    # scaffold creates items with verification status "available"
    assert "available" in summary
    assert "available" in readme


# Claim map: absent in alpha — claim-evidence mapping not generated

def test_summary_claim_map_absent_in_alpha(tmp_path):
    pkg = _make_package_with_evidence(tmp_path)
    readme, summary = _summarize_and_read(pkg)
    # Alpha contract: no claim maps. The rendered summary must not surface a
    # claim-evidence map section at all (neither as content nor as a header).
    assert "## Claim-evidence map" not in summary
    assert "## Claim-evidence map" not in readme
    assert "claim_map.json" not in summary
    assert "claim_map.json" not in readme


def test_summary_no_claim_status_counts_without_claim_map(tmp_path):
    pkg = _make_package_with_evidence(tmp_path)
    readme, summary = _summarize_and_read(pkg)
    # Without claim_map, no status counts appear
    assert "by status:" not in summary


def test_summary_no_fail_section_when_no_claim_map(tmp_path):
    pkg = _make_package_with_evidence(tmp_path)
    readme, summary = _summarize_and_read(pkg)
    assert "FAIL (evidence contradicts claim)" not in summary


def test_summary_evidence_index_present(tmp_path):
    pkg = _make_package_with_evidence(tmp_path)
    readme, summary = _summarize_and_read(pkg)
    assert "evidence_index" in summary


# Tool trace: entry count, tool IDs, exit status breakdown, failure warning

def test_summary_tool_trace_entry_count(tmp_path):
    from aieng.provenance.tool_trace_writer import record_trace_package
    pkg = _make_package_with_evidence(tmp_path)
    record_trace_package(pkg, tool_id="freecad", tool_role="cad_runtime", step_name="step_a", exit_status="success")
    record_trace_package(pkg, tool_id="gmsh", tool_role="solver", step_name="step_b", exit_status="success")
    readme, summary = _summarize_and_read(pkg)
    assert "2 step(s) recorded" in summary
    assert "2 step(s) recorded" in readme


def test_summary_tool_trace_tool_ids_listed(tmp_path):
    from aieng.provenance.tool_trace_writer import record_trace_package
    pkg = _make_package_with_evidence(tmp_path)
    record_trace_package(pkg, tool_id="freecad", tool_role="cad_runtime", step_name="export", exit_status="success")
    readme, summary = _summarize_and_read(pkg)
    assert "freecad" in summary
    assert "freecad" in readme


def test_summary_tool_trace_exit_status_breakdown(tmp_path):
    from aieng.provenance.tool_trace_writer import record_trace_package
    pkg = _make_package_with_evidence(tmp_path)
    record_trace_package(pkg, tool_id="freecad", tool_role="cad_runtime", step_name="step_a", exit_status="success")
    readme, summary = _summarize_and_read(pkg)
    assert "exit statuses:" in summary
    assert "success" in summary


def test_summary_tool_trace_failure_warning(tmp_path):
    from aieng.provenance.tool_trace_writer import record_trace_package
    pkg = _make_package_with_evidence(tmp_path)
    record_trace_package(pkg, tool_id="gmsh", tool_role="solver", step_name="mesh", exit_status="failure")
    readme, summary = _summarize_and_read(pkg)
    assert "WARNING" in summary
    assert "failure" in summary


def test_summary_tool_trace_absent_note(tmp_path):
    pkg = _make_package_with_evidence(tmp_path)
    readme, summary = _summarize_and_read(pkg)
    assert "no external tool" in summary.lower() or "absent" in summary.lower()
    assert "no external tool" in readme.lower() or "absent" in readme.lower()


def test_summary_phase15d_content_in_both_outputs(tmp_path):
    from aieng.results.evidence_writer import record_evidence_package
    from aieng.provenance.tool_trace_writer import record_trace_package
    pkg = _make_package_with_evidence(tmp_path)
    record_evidence_package(
        pkg,
        evidence_id="ev_solver_x",
        evidence_type="solver_result",
        producer_kind="external_solver",
        producer_tool="freecad",
        artifact_kind="result_file",
        artifact_path="results/out.vtk",
        claim_support=["claim_solver_result_001"],
    )
    record_trace_package(pkg, tool_id="freecad", tool_role="solver", step_name="run", exit_status="success")
    readme, summary = _summarize_and_read(pkg)
    for content in (readme, summary):
        assert "by type:" in content
        assert "by producer kind:" in content
        assert "exit statuses:" in content
