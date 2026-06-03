"""Strict @part / @artifact mention binding (v1) — pure helper coverage."""

from app.agent_autopilot.mention_binding import (
    bindings_to_targets,
    build_mention_bindings,
    mention_status_word,
)


def _part(value: str) -> dict:
    return {"kind": "part", "raw": f"@part:{value}", "value": value}


def _artifact(value: str) -> dict:
    return {"kind": "artifact", "raw": f"@artifact:{value}", "value": value}


def test_known_part_resolves_with_source_and_canonical_id() -> None:
    bindings = build_mention_bindings(
        [_part("bracket")],
        part_indexes=[("cad.named_parts", ["bracket", "rib"])],
    )
    assert len(bindings) == 1
    b = bindings[0]
    assert b["kind"] == "part"
    assert b["known"] is True
    assert b["source"] == "cad.named_parts"
    assert b["canonical_id"] == "bracket"
    assert b["reason"] is None
    assert b["mention"] == "@part:bracket"


def test_unknown_part_is_false_with_reason() -> None:
    bindings = build_mention_bindings(
        [_part("ghost")],
        part_indexes=[("cad.named_parts", ["bracket"]), ("topology_map", ["bracket", "rib"])],
    )
    b = bindings[0]
    assert b["known"] is False
    assert b["source"] is None
    assert b["canonical_id"] is None
    assert "not found in cad.named_parts, topology_map" in b["reason"]


def test_unavailable_context_is_null_not_false() -> None:
    # No index at all (None) → unverified, never a false negative.
    bindings = build_mention_bindings([_part("bracket")], part_indexes=None)
    b = bindings[0]
    assert b["known"] is None
    assert b["reason"] == "no binding context available"
    # An empty index list is likewise treated as "no context".
    assert build_mention_bindings([_part("x")], part_indexes=[])[0]["known"] is None


def test_available_but_empty_index_is_false() -> None:
    # A real but empty parts list means the part is genuinely absent.
    bindings = build_mention_bindings([_part("bracket")], part_indexes=[("cad.named_parts", [])])
    assert bindings[0]["known"] is False


def test_topology_map_source_matches() -> None:
    bindings = build_mention_bindings(
        [_part("rib")],
        part_indexes=[("cad.named_parts", ["bracket"]), ("topology_map", ["rib"])],
    )
    assert bindings[0]["known"] is True
    assert bindings[0]["source"] == "topology_map"


def test_case_insensitive_match_keeps_index_casing() -> None:
    bindings = build_mention_bindings(
        [_part("Bracket")],
        part_indexes=[("cad.named_parts", ["bracket"])],
    )
    assert bindings[0]["known"] is True
    assert bindings[0]["canonical_id"] == "bracket"


def test_known_and_unknown_artifacts() -> None:
    bindings = build_mention_bindings(
        [_artifact("model.glb"), _artifact("missing.step")],
        artifact_indexes=[("workspace_artifacts", ["model.glb", "result.step"])],
    )
    assert bindings[0]["known"] is True
    assert bindings[0]["source"] == "workspace_artifacts"
    assert bindings[1]["known"] is False


def test_unavailable_artifact_context_is_null() -> None:
    bindings = build_mention_bindings([_artifact("model.glb")], artifact_indexes=None)
    assert bindings[0]["known"] is None


def test_multiple_mentions_preserve_order_and_skip_other_kinds() -> None:
    mentions = [
        _part("bracket"),
        {"kind": "face", "raw": "@face:f1", "value": "f1"},   # out of scope → skipped
        _artifact("model.glb"),
        {"kind": "part", "raw": "@part:", "value": ""},       # malformed → skipped
        "oops",                                               # malformed → skipped
        _part("ghost"),
    ]
    bindings = build_mention_bindings(
        mentions,
        part_indexes=[("cad.named_parts", ["bracket"])],
        artifact_indexes=[("workspace_artifacts", ["model.glb"])],
    )
    assert [(b["kind"], b["value"], b["known"]) for b in bindings] == [
        ("part", "bracket", True),
        ("artifact", "model.glb", True),
        ("part", "ghost", False),
    ]


def test_non_list_mentions_returns_empty() -> None:
    assert build_mention_bindings(None) == []
    assert build_mention_bindings("oops") == []


def test_bindings_to_targets_groups_by_kind() -> None:
    bindings = build_mention_bindings(
        [_part("bracket"), _artifact("model.glb")],
        part_indexes=[("cad.named_parts", ["bracket"])],
        artifact_indexes=None,
    )
    targets = bindings_to_targets(bindings)
    assert [t["value"] for t in targets["parts"]] == ["bracket"]
    assert targets["parts"][0]["canonical_id"] == "bracket"
    assert [t["value"] for t in targets["artifacts"]] == ["model.glb"]
    assert targets["artifacts"][0]["known"] is None  # no artifact context


def test_status_word() -> None:
    assert mention_status_word(True) == "known"
    assert mention_status_word(False) == "not found"
    assert mention_status_word(None) == "unverified"
