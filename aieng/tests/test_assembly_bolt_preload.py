"""Honest bolt-preload modeling contract for assembly CAE (#199)."""
from __future__ import annotations

from aieng.converters.assembly_cae import (
    build_assembly_cae_model,
    build_bolt_preload_report,
    generate_assembly_solver_deck,
)


def _model(*connections: dict) -> dict:
    return {"connections": list(connections)}


def test_report_records_intent_as_unsupported_without_modeling() -> None:
    report = build_bolt_preload_report(_model(
        {"connection_id": "c1", "type": "bolted_proxy", "interface_a": "if_a", "interface_b": "if_b",
         "bolt_preload": {"intent_present": True, "axial_force_n": 5000.0, "method": "axial_force",
                          "fastener_id": "bolt_1", "modeled": False}},
        {"connection_id": "c2", "type": "bolted_proxy", "interface_a": "if_c", "interface_b": "if_d",
         "bolt_preload": {"intent_present": False, "axial_force_n": None, "modeled": False}},
        {"connection_id": "c3", "type": "rigid_tie"},  # non-bolted -> excluded
    ), deck_status="skipped")

    assert report["bolt_preload_modeled"] is False
    assert report["deck_representation"] == "unsupported"
    assert report["summary"] == {"bolted_connections": 2, "with_preload_intent": 1, "modeled": 0}
    by_id = {c["connection_id"]: c for c in report["connections"]}
    assert set(by_id) == {"c1", "c2"}  # rigid_tie excluded
    assert by_id["c1"]["preload_intent_present"] is True
    assert by_id["c1"]["axial_force_n"] == 5000.0
    assert by_id["c1"]["fastener_id"] == "bolt_1"
    assert by_id["c1"]["interface_a"] == "if_a"
    assert by_id["c1"]["status"] == "unsupported"
    assert by_id["c2"]["status"] == "no_intent"
    assert report["honesty"]["torque_to_preload_certified"] is False
    assert report["honesty"]["fatigue_modeled"] is False


def test_bolt_preload_modeled_requires_deck_evidence_not_intent() -> None:
    # Intent alone never flips the flag...
    intent_only = build_bolt_preload_report(_model(
        {"connection_id": "c1", "type": "bolted_proxy",
         "bolt_preload": {"intent_present": True, "axial_force_n": 9000.0, "modeled": False}},
    ))
    assert intent_only["bolt_preload_modeled"] is False
    # ...only an actually-modeled connection does.
    modeled = build_bolt_preload_report(_model(
        {"connection_id": "c1", "type": "bolted_proxy",
         "bolt_preload": {"intent_present": True, "axial_force_n": 9000.0, "modeled": True}},
    ))
    assert modeled["bolt_preload_modeled"] is True
    assert modeled["summary"]["modeled"] == 1


def test_explicit_preload_intent_flows_through_model_build() -> None:
    asm = {
        "format": "aieng.assembly_ir", "unit": "mm",
        "parts": [{"id": "a"}, {"id": "b"}],
        "interfaces": [
            {"id": "if_a", "part_id": "a", "topology_refs": {"face_ids": ["fa"]}},
            {"id": "if_b", "part_id": "b", "topology_refs": {"face_ids": ["fb"]}},
        ],
        "connections": [{
            "id": "c1", "type": "bolted_proxy", "part_a": "a", "part_b": "b",
            "interface_a": "if_a", "interface_b": "if_b", "behavior": ["load_transfer"],
            "preload": {"axial_force_n": 7000.0, "fastener_id": "M8_1"},
        }],
    }
    model, _diag = build_assembly_cae_model(
        assembly=asm, part_registry={}, connection_graph={}, interface_resolution={},
        connection_geometry={}, setup_draft={},
    )
    bp = model["connections"][0]["bolt_preload"]
    assert bp["intent_present"] is True
    assert bp["axial_force_n"] == 7000.0
    assert bp["fastener_id"] == "M8_1"
    assert bp["modeled"] is False
    assert model["solver_hints"]["bolt_preload_modeled"] is False

    report = build_bolt_preload_report(model)
    assert report["summary"]["with_preload_intent"] == 1
    assert report["bolt_preload_modeled"] is False


def test_preload_is_not_inferred_from_designation() -> None:
    asm = {
        "format": "aieng.assembly_ir", "unit": "mm",
        "parts": [{"id": "a"}, {"id": "b"}],
        "interfaces": [
            {"id": "if_a", "part_id": "a", "topology_refs": {"face_ids": ["fa"]}},
            {"id": "if_b", "part_id": "b", "topology_refs": {"face_ids": ["fb"]}},
        ],
        # A bolt designation / standard-part reference but NO explicit preload block.
        "connections": [{
            "id": "c1", "type": "bolted_proxy", "part_a": "a", "part_b": "b",
            "interface_a": "if_a", "interface_b": "if_b", "behavior": ["load_transfer"],
            "standard_part": "hex_bolt_M8", "designation": "M8x1.25",
        }],
    }
    model, _diag = build_assembly_cae_model(
        assembly=asm, part_registry={}, connection_graph={}, interface_resolution={},
        connection_geometry={}, setup_draft={},
    )
    assert model["connections"][0]["bolt_preload"]["intent_present"] is False
    report = build_bolt_preload_report(model)
    assert report["connections"][0]["status"] == "no_intent"
    assert report["honesty"]["preload_inferred_from_designation"] is False


def test_deck_generation_notes_preload_intent_as_unsupported() -> None:
    model = {
        "parts": [{"part_id": "a", "mesh_ref": "m/a.inp"}, {"part_id": "b", "mesh_ref": "m/b.inp"}],
        "connections": [{
            "connection_id": "c1", "proxy_model_type": "bolted_connector_proxy",
            "enabled_for_solver": True, "interface_a": "if_a", "interface_b": "if_b",
            "bolt_preload": {"intent_present": True, "axial_force_n": 7000.0, "modeled": False},
        }],
    }
    deck, diag = generate_assembly_solver_deck(model, available_members={"m/a.inp", "m/b.inp"})
    assert diag["status"] == "generated"
    assert diag["metadata"]["bolt_preload_modeled"] is False
    assert "c1" in diag["bolt_preload_intents_unsupported"]
    assert deck is not None and "BOLT PRELOAD INTENT c1" in deck
