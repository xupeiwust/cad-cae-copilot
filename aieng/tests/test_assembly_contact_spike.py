"""Honesty pins for the assembly nonlinear-contact spike (#198).

The spike concludes (see docs/assembly_contact_spike.md) that no real nonlinear
contact case can be modeled in the v0 stack; these tests pin that the
contact-unavailable path stays explicit and that `contact_physics_modeled` is
never claimed true from the proxy path.
"""
from __future__ import annotations

from aieng.converters.assembly_cae import (
    build_assembly_cae_model,
    generate_assembly_solver_deck,
)


def _contact_assembly() -> dict:
    return {
        "format": "aieng.assembly_ir", "unit": "mm",
        "parts": [{"id": "a"}, {"id": "b"}],
        "interfaces": [
            {"id": "if_a", "part_id": "a", "topology_refs": {"face_ids": ["fa"]}},
            {"id": "if_b", "part_id": "b", "topology_refs": {"face_ids": ["fb"]}},
        ],
        "connections": [{
            "id": "c1", "type": "contact_proxy", "part_a": "a", "part_b": "b",
            "interface_a": "if_a", "interface_b": "if_b", "behavior": ["load_transfer"],
        }],
    }


def test_contact_assembly_never_claims_contact_physics() -> None:
    model, diag = build_assembly_cae_model(
        assembly=_contact_assembly(), part_registry={}, connection_graph={},
        interface_resolution={}, connection_geometry={}, setup_draft={},
    )
    conn = model["connections"][0]
    # contact is an explicitly unsupported proxy and is never solver-enabled
    assert conn["proxy_model_type"] == "unsupported_contact_proxy"
    assert conn["enabled_for_solver"] is False
    assert "unsupported_proxy_type" in (conn["disabled_reason"] or "")
    # honesty: contact physics is never modeled by the proxy path
    assert model["solver_hints"]["contact_physics_modeled"] is False
    assert any("contact" in lim.lower() for lim in model["limitations"])


def test_contact_only_assembly_generates_no_solver_deck() -> None:
    model, _ = build_assembly_cae_model(
        assembly=_contact_assembly(), part_registry={}, connection_graph={},
        interface_resolution={}, connection_geometry={}, setup_draft={},
    )
    deck, deck_diag = generate_assembly_solver_deck(model)
    # no enabled connection -> no deck faked, and the deck diagnostics stay honest
    assert deck is None
    assert deck_diag["status"] == "skipped"
    assert deck_diag["metadata"]["contact_physics_modeled"] is False
