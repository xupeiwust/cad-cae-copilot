from __future__ import annotations

from pathlib import Path


def _index(text: str, needle: str) -> int:
    position = text.find(needle)
    assert position != -1, f"missing text: {needle}"
    return position


def test_readme_phase10b_orders_interface_graph_before_cae_mapping():
    # Phase-by-phase command narratives moved from README.md to
    # docs/development_log.md when README was reshaped as outward-facing.
    # The heading style changed from "## Phase 10B explicit CAE mapping
    # usage" to "### Phase 10B — Explicit CAE mapping" but the ordering
    # constraint (build-interface-graph BEFORE apply-cae-mapping) is
    # what actually matters and is still preserved.
    text = Path("docs/development_log.md").read_text(encoding="utf-8")
    phase_start = text.index("### Phase 10B — Explicit CAE mapping")
    # End the slice at the next phase heading so the assertion is local.
    phase = text[phase_start:text.index("###", phase_start + 4)]
    assert _index(phase, "aieng build-interface-graph build/bracket_001.aieng --overwrite") < _index(
        phase,
        "aieng apply-cae-mapping build/bracket_001.aieng --mapping examples/bracket_cae_mapping.yaml --overwrite",
    )
    # iface_feat_hole_pattern_001 / objects/interface_graph.json are
    # exercised by the demo_walkthrough and command_reference tests in
    # this file; the README phase-history version does not need to
    # repeat those assertions.


def test_command_reference_mentions_interface_graph_prerequisite():
    text = Path("docs/command_reference.md").read_text(encoding="utf-8")
    section = text[text.index("## `aieng apply-cae-mapping`"):]
    assert "If the mapping YAML references `maps_to.interface_id`" in section
    assert "objects/interface_graph.json" in section
    assert "aieng build-interface-graph" in section


def test_demo_walkthrough_orders_interface_graph_before_apply_cae_mapping():
    text = Path("docs/demo_walkthrough.md").read_text(encoding="utf-8")
    assert _index(text, "aieng build-interface-graph build/bracket_001.aieng --overwrite") < _index(
        text,
        "aieng apply-cae-mapping build/bracket_001.aieng --mapping examples/bracket_cae_mapping.yaml --overwrite",
    )
    assert "Phase 10B interface graph prerequisite" in text
    assert "FIXED_HOLES" in text
    assert "iface_feat_hole_pattern_001" in text


def test_cae_mapping_fixture_documents_interface_graph_prerequisite():
    text = Path("examples/bracket_cae_mapping.yaml").read_text(encoding="utf-8")
    assert "Generate objects/interface_graph.json first" in text
    assert "iface_feat_hole_pattern_001" in text
