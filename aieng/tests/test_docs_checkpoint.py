from __future__ import annotations

from pathlib import Path


def _readme_or_log() -> str:
    """README + development_log combined.

    Phase-specific content (phase numbers, command-by-phase narratives,
    historical positioning statements) was intentionally moved from
    README.md into docs/development_log.md when the README was rewritten
    as an outward-facing project doc (commit 7dc934b). Doc-checkpoint
    tests that previously asserted strings in README should now succeed
    if the string lives in either file — the guarantee is "this content
    is recorded in the repo", not "this content is in README.md".
    """
    return (
        Path("README.md").read_text(encoding="utf-8")
        + "\n\n"
        + Path("docs/development_log.md").read_text(encoding="utf-8")
    )


def test_mvp_checkpoint_exists():
    assert Path("docs/mvp_checkpoint.md").exists()


def test_roadmap_exists():
    assert Path("docs/roadmap.md").exists()


def test_command_reference_exists():
    assert Path("docs/command_reference.md").exists()


def test_readme_links_to_checkpoint_docs():
    # README was reshaped as outward-facing; mvp_checkpoint.md is now an
    # internal-history doc not linked from the front page. The other two
    # remain documented from README.
    text = _readme_or_log()
    assert "docs/roadmap.md" in text
    assert "docs/command_reference.md" in text


def test_readme_links_to_core_docs():
    # The outward-facing README links to the central product/architecture
    # docs. Specialist docs (rigorous-interop checklist, reference scenario,
    # demo walkthrough, ai-understanding benchmark) still exist on disk —
    # they're just not all surfaced from the front page anymore.
    text = Path("README.md").read_text(encoding="utf-8")
    assert "docs/core_position.md" in text
    assert "docs/architecture.md" in text
    # Specialist docs must exist so internal/development readers can find them.
    for specialist in (
        "docs/rigorous_interop_acceptance_checklist.md",
        "docs/reference_scenario_bracket.md",
        "docs/demo_walkthrough.md",
        "docs/ai_understanding_benchmark.md",
    ):
        assert Path(specialist).exists(), f"missing {specialist}"


def test_mvp_checkpoint_covers_all_phases():
    text = Path("docs/mvp_checkpoint.md").read_text(encoding="utf-8")
    for phase in ["Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5A", "Phase 5B", "Phase 5C", "Phase 5D"]:
        assert phase in text, f"missing {phase} in mvp_checkpoint.md"


def test_mvp_checkpoint_distinguishes_mock_rule_user():
    text = Path("docs/mvp_checkpoint.md").read_text(encoding="utf-8")
    assert "mock-based" in text.lower() or "Mock-based" in text
    assert "rule-based" in text.lower() or "Rule-based" in text
    assert "user-provided" in text.lower() or "User-provided" in text
    assert "not implemented" in text.lower()


def test_roadmap_contains_all_required_phases():
    text = Path("docs/roadmap.md").read_text(encoding="utf-8")
    for phase in ["Phase 6A", "Phase 6B", "Phase 7", "Phase 8", "Phase 9", "Phase 10"]:
        assert phase in text, f"missing {phase} in roadmap.md"


def test_roadmap_phases_have_goal_and_success_criteria():
    text = Path("docs/roadmap.md").read_text(encoding="utf-8")
    assert "Goal" in text
    assert "Success criteria" in text
    assert "Risks" in text
    assert "What not to implement" in text or "What to implement" in text


def test_command_reference_covers_all_commands():
    text = Path("docs/command_reference.md").read_text(encoding="utf-8")
    for cmd in ["aieng init", "aieng import-step", "aieng extract-topology",
                "aieng recognize-features", "aieng apply-context",
            "aieng summarize", "aieng propose-patch", "aieng apply-patch",
            "aieng build-allowed-operations-catalog",
            "aieng export-updated-deck", "aieng write-mesh-handoff", "aieng write-evidence-report", "aieng validate"]:
        assert cmd in text, f"missing '{cmd}' in command_reference.md"


def test_command_reference_documents_nature_of_each_command():
    text = Path("docs/command_reference.md").read_text(encoding="utf-8")
    assert "Mock-based" in text or "mock-based" in text
    assert "Rule-based" in text or "rule-based" in text
    assert "User-context-based" in text or "user-context-based" in text


def test_command_reference_import_commands_state_global_evidence_only_policy():
    text = Path("docs/command_reference.md").read_text(encoding="utf-8")
    assert "global import policy: evidence-only by default" in text
    assert "human review" in text.lower() or "Claim proposals require human review" in text


def test_architecture_declares_global_evidence_only_import_policy():
    text = Path("docs/architecture.md").read_text(encoding="utf-8")
    assert "Global import policy for this architecture" in text
    assert "Import commands are evidence-only by default" in text
    assert "must not automatically advance claim status" in text


def test_interop_matrix_marks_evidence_only_as_resolved_policy():
    text = Path("docs/interop_standards_matrix.md").read_text(encoding="utf-8")
    assert "## Resolved policy decision" in text
    assert "Import pathways are evidence-only by default" in text
    assert "do not automatically change claim status" in text


def test_readme_mentions_phase_13_semantic_patch_scaffold():
    text = _readme_or_log()
    assert "Phase 13B" in text
    assert "semantic parameter update only" in text
    assert "export-updated-deck" in text


def test_docs_clarify_external_cae_execution_boundary():
    # The execution-boundary constraint must be stated somewhere in the
    # documentation. The exact wording has evolved across multiple docs;
    # what matters is that the boundary is documented per-source.
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    future = Path("docs/future_package_structure.md").read_text(encoding="utf-8")
    log = Path("docs/development_log.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmap.md").read_text(encoding="utf-8")

    assert "External CAE responsibility" in log
    assert "not intended to become a mesher" in roadmap
    assert "External CAD/CAE software executes" in architecture
    assert "should not be presented as the mesher or solver" in future


def test_core_position_says_aieng_describes_not_executes_cae():
    text = Path("docs/core_position.md").read_text(encoding="utf-8")
    assert "describe, reference, configure, and record" in text
    assert "should not become the mesher or solver" in text


def test_mvp_checkpoint_mentions_phase_13_commands_and_updated_deck():
    text = Path("docs/mvp_checkpoint.md").read_text(encoding="utf-8")
    assert "Phase 13A" in text
    assert "Phase 13B" in text
    assert "Phase 13C" in text
    assert "aieng apply-patch" in text
    assert "aieng export-updated-deck" in text
    assert "simulation/updated_deck.inp" in text


def test_readme_links_to_first_benchmark_result():
    # The specific bracket_001_manual results run is now linked from
    # development_log + benchmark_runs/, not from the outward README.
    text = _readme_or_log()
    assert "results_run_001.md" in text
    assert "benchmark_runs/bracket_001_manual/results_run_001.md" in text


def test_readme_first_benchmark_result_has_score_table():
    # The outward-facing README carries a small benchmark summary table.
    # The detailed scoring narrative lives in development_log + benchmarks/.
    text = _readme_or_log()
    assert "First Benchmark Result" in text
    assert "16 / 16" in text
    assert "Honesty" in text or "honesty" in text
    assert "actionable" in text


# ---------------------------------------------------------------------------
# Geometry backend contract document (Phase 7A+)
# ---------------------------------------------------------------------------

def test_geometry_backend_contract_exists():
    assert Path("docs/geometry_backend_contract.md").exists()


def test_geometry_backend_contract_mentions_geometry_backend():
    text = Path("docs/geometry_backend_contract.md").read_text(encoding="utf-8")
    assert "GeometryBackend" in text


def test_geometry_backend_contract_mentions_mock_backend():
    text = Path("docs/geometry_backend_contract.md").read_text(encoding="utf-8")
    assert "mock" in text.lower()
    assert "MockGeometryBackend" in text


def test_geometry_backend_contract_mentions_occ_placeholder():
    text = Path("docs/geometry_backend_contract.md").read_text(encoding="utf-8")
    assert "occ" in text.lower()
    assert "placeholder" in text.lower()


def test_geometry_backend_contract_mentions_real_step_parsing():
    text = Path("docs/geometry_backend_contract.md").read_text(encoding="utf-8")
    assert "real_step_parsing" in text


def test_geometry_backend_contract_says_must_not_infer_design_intent():
    text = Path("docs/geometry_backend_contract.md").read_text(encoding="utf-8")
    assert "design intent" in text.lower() or "infer design intent" in text.lower()
    assert "must not" in text.lower()


def test_readme_links_to_geometry_backend_contract():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "docs/geometry_backend_contract.md" in text


# ---------------------------------------------------------------------------
# OCP topology demo (Phase 7C)
# ---------------------------------------------------------------------------

def test_ocp_topology_demo_doc_exists():
    assert Path("docs/ocp_topology_demo.md").exists()


def test_ocp_topology_demo_script_exists():
    assert Path("scripts/run_ocp_topology_demo.py").exists()


def test_ocp_topology_demo_doc_mentions_geometry_backends():
    text = Path("docs/ocp_topology_demo.md").read_text(encoding="utf-8")
    assert "geometry-backends" in text


def test_ocp_topology_demo_doc_mentions_experimental():
    text = Path("docs/ocp_topology_demo.md").read_text(encoding="utf-8")
    assert "experimental" in text.lower()


def test_ocp_topology_demo_doc_mentions_limitations():
    text = Path("docs/ocp_topology_demo.md").read_text(encoding="utf-8")
    assert "Limitation" in text or "limitation" in text


def test_ocp_topology_demo_doc_mentions_real_step_parsing():
    text = Path("docs/ocp_topology_demo.md").read_text(encoding="utf-8")
    assert "real_step_parsing" in text


def test_ocp_topology_demo_doc_mentions_experimental_real_extraction():
    text = Path("docs/ocp_topology_demo.md").read_text(encoding="utf-8")
    assert "experimental_real_extraction" in text


def test_ocp_topology_demo_script_mentions_detect_occ_runtime():
    text = Path("scripts/run_ocp_topology_demo.py").read_text(encoding="utf-8")
    assert "detect_occ_runtime" in text


def test_ocp_demo_script_exits_cleanly_without_arguments():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/run_ocp_topology_demo.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Usage" in result.stdout or "usage" in result.stdout or "step" in result.stdout.lower()


def test_readme_links_to_ocp_topology_demo():
    text = _readme_or_log()
    assert "docs/ocp_topology_demo.md" in text


def test_readme_mentions_semantic_task_understanding_layer():
    # The "semantic task-understanding layer" framing is preserved in
    # core_position + architecture + mvp_checkpoint, not in the outward
    # README (which uses lighter phrasing for first-impression clarity).
    core = Path("docs/core_position.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    assert "semantic task-understanding layer" in core
    assert "semantic task-understanding layer" in architecture


def test_core_position_mentions_non_replacement_of_step_cad_cae():
    text = Path("docs/core_position.md").read_text(encoding="utf-8")
    assert "does not replace STEP" in text
    assert "complements STEP/AP242/CAE decks" in text


def test_architecture_mentions_semantic_layer_process_chain():
    text = Path("docs/architecture.md").read_text(encoding="utf-8")
    assert "semantic task-understanding layer" in text
    assert "cax process-chain" in text.lower()


# ---------------------------------------------------------------------------
# Phase 8A benchmark documentation
# ---------------------------------------------------------------------------

def test_benchmark_aieng_input_index_mentions_visual_annotation():
    text = Path("benchmark_runs/bracket_001_manual/aieng_input_index.md").read_text(encoding="utf-8")
    assert "visual/annotation_layers.json" in text


def test_benchmark_aieng_input_index_describes_annotation_as_metadata():
    text = Path("benchmark_runs/bracket_001_manual/aieng_input_index.md").read_text(encoding="utf-8")
    assert "annotation metadata" in text.lower() or "metadata only" in text.lower()


def test_benchmark_instructions_includes_build_visual_index():
    text = Path("benchmark_runs/bracket_001_manual/instructions.md").read_text(encoding="utf-8")
    assert "build-visual-index" in text


def test_benchmark_expected_observations_mentions_visual_annotation():
    text = Path("benchmark_runs/bracket_001_manual/expected_observations.md").read_text(encoding="utf-8")
    assert "visual annotation" in text.lower() or "annotation_layers" in text


def test_benchmark_expected_observations_distinguishes_annotation_from_rendering():
    text = Path("benchmark_runs/bracket_001_manual/expected_observations.md").read_text(encoding="utf-8")
    assert "rendering" in text.lower()
    assert "not_generated" in text or "no rendering" in text.lower() or "annotation metadata" in text.lower()


def test_benchmark_questions_include_visual_annotation_question():
    text = Path("benchmarks/questions.md").read_text(encoding="utf-8")
    assert "visual" in text.lower()
    assert "annotation" in text.lower()


def test_benchmark_aieng_expected_capabilities_mentions_visual_annotation():
    text = Path("benchmarks/aieng_expected_capabilities.md").read_text(encoding="utf-8")
    assert "visual" in text.lower()
    assert "annotation" in text.lower()


def test_benchmark_prompt_template_includes_visual_annotation_layers():
    text = Path("benchmark_runs/bracket_001_manual/ai_understanding_benchmark_prompt_template.md").read_text(encoding="utf-8")
    assert "visual/annotation_layers.json" in text

def test_docs_position_aieng_as_cad_cae_side_export_layer():
    # The canonical phrase lives in the positioning docs; the outward
    # README uses lighter user-facing language. The constraint is that
    # the positioning is documented in core_position + architecture.
    core = Path("docs/core_position.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")

    assert "CAD/CAE-side semantic export and evidence" in core
    assert "CAD/CAE-side semantic export and evidence" in architecture


def test_docs_say_mcp_is_optional_access_interface_not_core_product():
    # MCP positioning is documented in mcp_server.md + architecture +
    # roadmap; the outward README mentions MCP differently.
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    mcp_doc = Path("docs/mcp_server.md").read_text(encoding="utf-8")
    roadmap = Path("docs/roadmap.md").read_text(encoding="utf-8")

    assert "optional access interface" in architecture
    assert "optional access interface" in mcp_doc
    assert "not the core product" in mcp_doc
    assert "MCP is an optional access interface" in mcp_doc
    assert "not intended to become a mesher, solver, optimizer, planner, or agent runtime" in roadmap


def test_cad_cae_emitter_contract_exists_and_is_linked():
    # cad_cae_emitter_contract.md is a specialist doc. Outward README
    # no longer links it directly; the link survives in
    # development_log.md (the canonical historical record).
    assert Path("docs/cad_cae_emitter_contract.md").exists()
    assert "docs/cad_cae_emitter_contract.md" in _readme_or_log()


def test_cad_cae_emitter_contract_defines_capability_levels_and_missingness():
    text = Path("docs/cad_cae_emitter_contract.md").read_text(encoding="utf-8")
    for level in ["L0", "L1", "L2", "L3", "L4", "L5"]:
        assert level in text
    assert "best-effort semantic conversion" in text
    assert "explicit missingness" in text
    assert "validation/completeness_report.json" in text


def test_docs_distinguish_agent_tools_from_core_product():
    # core_position carries the "house and windows" framing for the
    # package-vs-tools distinction; the contract doc carries the
    # not-core-product statement.
    core = Path("docs/core_position.md").read_text(encoding="utf-8")
    contract = Path("docs/cad_cae_emitter_contract.md").read_text(encoding="utf-8")
    assert "agent tools are windows" in core
    assert "the `.aieng` package is the house" in core
    assert "Agent-facing tools" in contract
    assert "not the core product" in contract


def test_agi_handoff_walkthrough_exists_and_is_linked():
    assert Path("docs/agi_handoff_walkthrough.md").exists()
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "docs/agi_handoff_walkthrough.md" in readme


def test_agi_handoff_walkthrough_covers_end_to_end_writeback_loop():
    text = Path("docs/agi_handoff_walkthrough.md").read_text(encoding="utf-8")
    for required in [
        "write-task-spec",
        "propose-patch",
        "write-external-tool-requirements",
        "write-evidence-scaffold",
        "record-evidence",
        "record-trace",
        "write-completeness-report",
        "validate",
    ]:
        assert required in text


def test_agi_handoff_walkthrough_preserves_execution_boundary():
    text = Path("docs/agi_handoff_walkthrough.md").read_text(encoding="utf-8")
    assert "External CAD/CAE tools execute outside `.aieng`" in text
    assert "not performed by `.aieng` core" in text
    assert "unsupported is not false" in text
    assert "mechanical_agent" in text


def test_emitter_contract_mentions_definition_sourced_mode():
    text = Path("docs/cad_cae_emitter_contract.md").read_text(encoding="utf-8")
    assert "Definition-sourced semantic emitter" in text
    assert "aieng define" in text
    assert "source_mode: definition" in text
    assert "does not generate geometry" in text


def test_readme_mentions_define_completeness_integration():
    # The `aieng define` command + completeness integration is
    # documented in command_reference + mvp_checkpoint, not in the
    # outward README (it's a specialist workflow).
    checkpoint = Path("docs/mvp_checkpoint.md").read_text(encoding="utf-8")
    command_ref = Path("docs/command_reference.md").read_text(encoding="utf-8")
    assert "aieng define" in checkpoint or "aieng define" in command_ref
    assert "validation/completeness_report.json" in checkpoint or "validation/completeness_report.json" in command_ref


def test_schema_versioning_doc_exists():
    assert Path("docs/schema_versioning.md").exists()


def test_rigorous_interop_acceptance_checklist_exists():
    assert Path("docs/rigorous_interop_acceptance_checklist.md").exists()


def test_rigorous_interop_acceptance_checklist_contains_core_gates():
    text = Path("docs/rigorous_interop_acceptance_checklist.md").read_text(encoding="utf-8")
    assert "Global import policy is evidence-only" in text
    assert "Roundtrip invariance test exists" in text
    assert "Claim decision thresholds are formalized per claim ID" in text
    assert "Rigorous Interop" in text


def test_rigorous_interop_checklist_declares_manual_maintenance_protocol():
    text = Path("docs/rigorous_interop_acceptance_checklist.md").read_text(encoding="utf-8")
    assert "## Maintenance Protocol (Required)" in text
    assert "manually maintained" in text
    assert "not fully self-validated by tests" in text
    assert "historical documentation instead of a live release gate" in text


def test_rigorous_interop_checklist_links_execution_issues():
    text = Path("docs/rigorous_interop_acceptance_checklist.md").read_text(encoding="utf-8")
    assert "## Issue Tracking" in text
    for issue_ref in ["#31", "#4", "#32", "#33", "#34"]:
        assert issue_ref in text


def test_schema_versioning_doc_contains_required_sections():
    text = Path("docs/schema_versioning.md").read_text(encoding="utf-8")
    for heading in [
        "# Schema Versioning Policy",
        "## Versioning Scheme",
        "## What Counts as Breaking",
        "## What Counts as Additive",
        "## Reader Policy",
        "## Schema-Level Version vs Resource-Level Version",
        "## Deprecation Policy",
        "## Const Guards and Breaking Changes",
        "## Pre-1.0 Expectations",
        "## Worked Examples",
    ]:
        assert heading in text, f"missing section {heading!r} in schema_versioning.md"


def test_schema_versioning_doc_contains_worked_examples():
    text = Path("docs/schema_versioning.md").read_text(encoding="utf-8")
    assert "task/task_spec.yaml" in text
    assert "optional field" in text.lower()
    assert "enum" in text.lower()
    assert "narrow" in text.lower()


def test_readme_and_mvp_checkpoint_link_schema_versioning_doc():
    # README is outward-facing; schema_versioning.md is a specialist doc
    # not linked from the front page. The reference is preserved in
    # mvp_checkpoint.md.
    checkpoint = Path("docs/mvp_checkpoint.md").read_text(encoding="utf-8")
    assert "schema_versioning.md" in checkpoint


def test_contributing_links_schema_versioning_doc():
    text = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "docs/schema_versioning.md" in text

