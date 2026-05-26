"""Tests for aieng.audit_event."""

from __future__ import annotations

import json
from typing import Any

import pytest

from aieng.audit_event import (
    AUDIT_EVENT_TYPES,
    AUDIT_EVENTS_PATH,
    build_audit_event,
    parse_audit_events_jsonl,
    serialize_audit_events_jsonl,
    validate_audit_event,
)

_BASE_KWARGS: dict[str, Any] = dict(
    tool="cae.run_solver",
    event_type="solver_run_completed",
    status="completed",
    artifacts_written=["simulation/runs/run_001/outputs/result.frd"],
    evidence_created=["simulation/runs/run_001/outputs/result.frd"],
    state_changes={"run_id": "run_001"},
    geometry_revision=1,
    revalidation_status=None,
)

_VALID_EVENT = build_audit_event(**_BASE_KWARGS)


# ── build_audit_event ────────────────────────────────────────────────────────

class TestBuildAuditEvent:
    def test_required_fields_present(self) -> None:
        e = build_audit_event(**_BASE_KWARGS)
        for field in (
            "schema_version", "event_id", "timestamp", "tool", "event_type",
            "status", "artifacts_written", "evidence_created",
            "state_changes", "geometry_revision", "revalidation_status",
            "claim_advancement",
        ):
            assert field in e, f"missing field: {field!r}"

    def test_schema_version(self) -> None:
        assert build_audit_event(**_BASE_KWARGS)["schema_version"] == "0.1"

    def test_claim_advancement_always_none(self) -> None:
        assert build_audit_event(**_BASE_KWARGS)["claim_advancement"] == "none"

    def test_fields_propagated(self) -> None:
        e = build_audit_event(**_BASE_KWARGS)
        assert e["tool"] == "cae.run_solver"
        assert e["event_type"] == "solver_run_completed"
        assert e["status"] == "completed"
        assert e["geometry_revision"] == 1
        assert e["revalidation_status"] is None

    def test_event_id_auto_generated(self) -> None:
        e = build_audit_event(**_BASE_KWARGS)
        assert isinstance(e["event_id"], str) and len(e["event_id"]) > 0

    def test_event_id_unique_each_call(self) -> None:
        a = build_audit_event(**_BASE_KWARGS)
        b = build_audit_event(**_BASE_KWARGS)
        assert a["event_id"] != b["event_id"]

    def test_custom_event_id(self) -> None:
        e = build_audit_event(**_BASE_KWARGS, event_id="fixed-id")
        assert e["event_id"] == "fixed-id"

    def test_custom_timestamp(self) -> None:
        ts = "2026-01-01T00:00:00+00:00"
        e = build_audit_event(**_BASE_KWARGS, timestamp=ts)
        assert e["timestamp"] == ts

    def test_timestamp_iso_format(self) -> None:
        e = build_audit_event(**_BASE_KWARGS)
        assert "T" in e["timestamp"]

    def test_artifacts_written_list(self) -> None:
        e = build_audit_event(**_BASE_KWARGS)
        assert isinstance(e["artifacts_written"], list)

    def test_evidence_created_list(self) -> None:
        e = build_audit_event(**_BASE_KWARGS)
        assert isinstance(e["evidence_created"], list)

    def test_geometry_modified_event(self) -> None:
        e = build_audit_event(
            tool="cad.edit_parameter",
            event_type="geometry_modified",
            status="completed",
            artifacts_written=["geometry/source.step"],
            evidence_created=[],
            state_changes={"parameter": "length", "value": 15.0},
            geometry_revision=2,
            revalidation_status="stale",
        )
        assert e["event_type"] == "geometry_modified"
        assert e["claim_advancement"] == "none"

    def test_claim_proposal_created_event(self) -> None:
        e = build_audit_event(
            tool="claims.propose_update",
            event_type="claim_proposal_created",
            status="completed",
            artifacts_written=["claims/proposals/abc123.json"],
            evidence_created=[],
            state_changes={"claim_id": "c1", "proposed_status": "supported"},
            geometry_revision=None,
            revalidation_status=None,
        )
        assert e["event_type"] == "claim_proposal_created"
        assert e["claim_advancement"] == "none"

    def test_cae_summary_refreshed_event(self) -> None:
        e = build_audit_event(
            tool="postprocess.refresh_cae_summary",
            event_type="cae_summary_refreshed",
            status="completed",
            artifacts_written=["results/result_summary.json"],
            evidence_created=["results/result_summary.json"],
            state_changes={},
            geometry_revision=1,
            revalidation_status=None,
        )
        assert e["event_type"] == "cae_summary_refreshed"
        assert e["claim_advancement"] == "none"


# ── validate_audit_event ─────────────────────────────────────────────────────

class TestValidateAuditEvent:
    def test_valid_event_no_issues(self) -> None:
        assert validate_audit_event(_VALID_EVENT) == []

    def test_missing_field_reported(self) -> None:
        bad = {k: v for k, v in _VALID_EVENT.items() if k != "tool"}
        issues = validate_audit_event(bad)
        assert any("tool" in i for i in issues)

    def test_wrong_claim_advancement_reported(self) -> None:
        bad = {**_VALID_EVENT, "claim_advancement": "accepted"}
        issues = validate_audit_event(bad)
        assert any("claim_advancement" in i for i in issues)

    def test_non_list_artifacts_written_reported(self) -> None:
        bad = {**_VALID_EVENT, "artifacts_written": "not-a-list"}
        issues = validate_audit_event(bad)
        assert any("artifacts_written" in i for i in issues)

    def test_non_list_evidence_created_reported(self) -> None:
        bad = {**_VALID_EVENT, "evidence_created": None}
        issues = validate_audit_event(bad)
        assert any("evidence_created" in i for i in issues)

    def test_multiple_missing_fields(self) -> None:
        issues = validate_audit_event({})
        assert len(issues) >= len(("schema_version", "event_id", "tool"))


# ── parse_audit_events_jsonl ─────────────────────────────────────────────────

class TestParseAuditEventsJsonl:
    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_audit_events_jsonl("") == []

    def test_blank_lines_skipped(self) -> None:
        line = json.dumps(_VALID_EVENT, separators=(",", ":"))
        text = f"\n{line}\n\n"
        events = parse_audit_events_jsonl(text)
        assert len(events) == 1

    def test_malformed_line_skipped(self) -> None:
        good = json.dumps(_VALID_EVENT, separators=(",", ":"))
        text = "not-json\n" + good + "\n"
        events = parse_audit_events_jsonl(text)
        assert len(events) == 1
        assert events[0]["event_id"] == _VALID_EVENT["event_id"]

    def test_multiple_events_parsed(self) -> None:
        a = build_audit_event(**_BASE_KWARGS)
        b = build_audit_event(**_BASE_KWARGS)
        text = (
            json.dumps(a, separators=(",", ":")) + "\n"
            + json.dumps(b, separators=(",", ":")) + "\n"
        )
        events = parse_audit_events_jsonl(text)
        assert len(events) == 2

    def test_preserves_order(self) -> None:
        a = build_audit_event(**_BASE_KWARGS, event_id="first")
        b = build_audit_event(**_BASE_KWARGS, event_id="second")
        text = (
            json.dumps(a, separators=(",", ":")) + "\n"
            + json.dumps(b, separators=(",", ":")) + "\n"
        )
        events = parse_audit_events_jsonl(text)
        assert events[0]["event_id"] == "first"
        assert events[1]["event_id"] == "second"


# ── serialize_audit_events_jsonl ─────────────────────────────────────────────

class TestSerializeAuditEventsJsonl:
    def test_empty_iterable_returns_empty_string(self) -> None:
        assert serialize_audit_events_jsonl([]) == ""

    def test_one_event_one_line(self) -> None:
        text = serialize_audit_events_jsonl([_VALID_EVENT])
        lines = [l for l in text.splitlines() if l.strip()]
        assert len(lines) == 1

    def test_each_line_valid_json(self) -> None:
        events = [build_audit_event(**_BASE_KWARGS) for _ in range(3)]
        text = serialize_audit_events_jsonl(events)
        for line in text.splitlines():
            json.loads(line)  # must not raise

    def test_compact_no_extra_spaces(self) -> None:
        text = serialize_audit_events_jsonl([_VALID_EVENT])
        line = text.strip()
        assert ": " not in line  # compact separators

    def test_roundtrip(self) -> None:
        original = [build_audit_event(**_BASE_KWARGS) for _ in range(2)]
        text = serialize_audit_events_jsonl(original)
        recovered = parse_audit_events_jsonl(text)
        assert len(recovered) == len(original)
        for orig, rec in zip(original, recovered):
            assert orig["event_id"] == rec["event_id"]
            assert rec["claim_advancement"] == "none"


# ── vocabulary constants ─────────────────────────────────────────────────────

class TestVocabularyConstants:
    def test_audit_events_path(self) -> None:
        assert AUDIT_EVENTS_PATH == "audit/events.jsonl"

    def test_known_event_types(self) -> None:
        for t in ("geometry_modified", "solver_run_completed",
                  "cae_summary_refreshed", "claim_proposal_created"):
            assert t in AUDIT_EVENT_TYPES
