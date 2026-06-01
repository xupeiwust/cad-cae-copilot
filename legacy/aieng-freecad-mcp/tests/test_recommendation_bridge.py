"""Tests for the recommendation + verification subprocess bridges (Phase 38)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from freecad_mcp.aieng_bridge.recommendation import recommend_cad_modifications
from freecad_mcp.aieng_bridge.verification import (
    STRICTNESS_MODES,
    verify_cad_modifications,
)


# ---------------------------------------------------------------------------
# Subprocess.run fake -- captures argv and returns a crafted CompletedProcess.
# ---------------------------------------------------------------------------


class _FakeRun:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.captured_argv: list[str] | None = None
        self.captured_kwargs: dict[str, Any] | None = None

    def __call__(self, argv, **kwargs):  # mimics subprocess.run signature
        self.captured_argv = argv
        self.captured_kwargs = kwargs
        return subprocess.CompletedProcess(
            args=argv, returncode=self.returncode, stdout=self.stdout, stderr=self.stderr
        )


def _patch_run(target: str, fake: _FakeRun):
    return patch(target, side_effect=fake)


# ---------------------------------------------------------------------------
# recommend_cad_modifications
# ---------------------------------------------------------------------------


_REC_PAYLOAD = {
    "schema_version": "0.1",
    "ok": True,
    "package_path": "/tmp/p.aieng",
    "proposals": [
        {
            "proposal_id": "p_001",
            "rank": 1,
            "feature_ref": "back_wall",
            "action_type": "thin",
            "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
            "confidence": "high",
        }
    ],
    "skipped_features": [],
    "modification_vocabulary": ["thin", "thicken", "add_fillet"],
    "evidence": {"has_design_targets": True},
    "llm_summary": {"one_line": "1 proposal."},
    "warnings": [],
    "claim_policy": {
        "proposals_are_hypotheses": True,
        "requires_verification_simulation": True,
        "claims_advanced": False,
    },
}


def test_recommend_returns_parsed_payload(tmp_path: Path) -> None:
    fake = _FakeRun(stdout=json.dumps(_REC_PAYLOAD))
    with _patch_run("freecad_mcp.aieng_bridge.recommendation.subprocess.run", fake):
        result = recommend_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake"
        )
    assert result["ok"] is True
    assert result["recommendations"]["proposals"][0]["feature_ref"] == "back_wall"
    assert result["claim_policy"]["proposals_are_hypotheses"] is True


def test_recommend_subprocess_argv_shape(tmp_path: Path) -> None:
    fake = _FakeRun(stdout=json.dumps(_REC_PAYLOAD))
    with _patch_run("freecad_mcp.aieng_bridge.recommendation.subprocess.run", fake):
        recommend_cad_modifications(tmp_path / "x.aieng", aieng_cli="aieng-fake")
    argv = fake.captured_argv
    assert argv[0] == "aieng-fake"
    assert argv[1] == "recommend-cad-modifications"
    assert argv[2].endswith("x.aieng")
    assert "--output" in argv
    assert "json" in argv
    # Subprocess must not invoke a shell.
    assert fake.captured_kwargs.get("shell") is False


def test_recommend_handles_empty_stdout(tmp_path: Path) -> None:
    fake = _FakeRun(stdout="", stderr="boom", returncode=2)
    with _patch_run("freecad_mcp.aieng_bridge.recommendation.subprocess.run", fake):
        result = recommend_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake"
        )
    assert result["ok"] is False
    assert any("no stdout" in e for e in result["errors"])
    assert result["claim_policy"]["claims_advanced"] is False


def test_recommend_handles_invalid_json(tmp_path: Path) -> None:
    fake = _FakeRun(stdout="<<not json>>")
    with _patch_run("freecad_mcp.aieng_bridge.recommendation.subprocess.run", fake):
        result = recommend_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake"
        )
    assert result["ok"] is False
    assert any("parse" in e.lower() for e in result["errors"])


def test_recommend_handles_cli_not_found(tmp_path: Path, monkeypatch) -> None:
    # which() returns None and the importability probe must also fail.
    monkeypatch.setattr(
        "freecad_mcp.aieng_bridge.recommendation.shutil.which", lambda _name: None
    )

    def _raise_import(*_a, **_k):
        raise ImportError("aieng missing")

    monkeypatch.setattr(
        "freecad_mcp.aieng_bridge.recommendation._resolve_aieng_cli",
        lambda _override: None,
    )
    result = recommend_cad_modifications(tmp_path / "x.aieng")
    assert result["ok"] is False
    assert any("CLI is not available" in e for e in result["errors"])


def test_recommend_handles_timeout(tmp_path: Path) -> None:
    def _raise_timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="aieng-fake", timeout=1)

    with patch(
        "freecad_mcp.aieng_bridge.recommendation.subprocess.run", side_effect=_raise_timeout
    ):
        result = recommend_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake", timeout_seconds=1
        )
    assert result["ok"] is False
    assert any("timed out" in e for e in result["errors"])


def test_recommend_propagates_ok_false_payload(tmp_path: Path) -> None:
    """When the CLI reports ok=False (e.g. missing inputs), the bridge propagates that."""
    not_ok = dict(_REC_PAYLOAD)
    not_ok["ok"] = False
    fake = _FakeRun(stdout=json.dumps(not_ok), returncode=2)
    with _patch_run("freecad_mcp.aieng_bridge.recommendation.subprocess.run", fake):
        result = recommend_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake"
        )
    assert result["ok"] is False
    assert result["recommendations"]["ok"] is False
    assert result["exit_code"] == 2


# ---------------------------------------------------------------------------
# verify_cad_modifications
# ---------------------------------------------------------------------------


_VERIFY_PAYLOAD = {
    "schema_version": "0.1",
    "ok": True,
    "package_path": "/tmp/p.aieng",
    "strictness": "default",
    "verdicts": [
        {"proposal_id": "p_001", "verdict": "pass", "feature_ref": "back_wall"}
    ],
    "summary": {"pass": 1, "warn": 0, "fail": 0, "total": 1},
    "warnings": [],
    "claim_policy": {
        "verification_is_pre_execution": True,
        "verification_does_not_replace_resimulation": True,
        "geometry_kernel_checks_not_performed": True,
        "claims_advanced": False,
    },
}


def test_verify_returns_parsed_payload(tmp_path: Path) -> None:
    fake = _FakeRun(stdout=json.dumps(_VERIFY_PAYLOAD))
    with _patch_run("freecad_mcp.aieng_bridge.verification.subprocess.run", fake):
        result = verify_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake"
        )
    assert result["ok"] is True
    assert result["summary"]["pass"] == 1
    assert result["claim_policy"]["geometry_kernel_checks_not_performed"] is True


def test_verify_ok_false_when_any_proposal_fails(tmp_path: Path) -> None:
    payload = dict(_VERIFY_PAYLOAD)
    payload["summary"] = {"pass": 0, "warn": 0, "fail": 1, "total": 1}
    fake = _FakeRun(stdout=json.dumps(payload))
    with _patch_run("freecad_mcp.aieng_bridge.verification.subprocess.run", fake):
        result = verify_cad_modifications(
            tmp_path / "x.aieng", aieng_cli="aieng-fake"
        )
    assert result["ok"] is False


def test_verify_rejects_unknown_strictness(tmp_path: Path) -> None:
    result = verify_cad_modifications(
        tmp_path / "x.aieng", aieng_cli="aieng-fake", strictness="paranoid"
    )
    assert result["ok"] is False
    assert any("strictness" in e for e in result["errors"])
    assert result["claim_policy"]["claims_advanced"] is False


def test_verify_subprocess_argv_shape_default(tmp_path: Path) -> None:
    fake = _FakeRun(stdout=json.dumps(_VERIFY_PAYLOAD))
    with _patch_run("freecad_mcp.aieng_bridge.verification.subprocess.run", fake):
        verify_cad_modifications(tmp_path / "x.aieng", aieng_cli="aieng-fake")
    argv = fake.captured_argv
    assert argv[0] == "aieng-fake"
    assert argv[1] == "verify-cad-modifications"
    assert argv[2].endswith("x.aieng")
    assert "--strictness" in argv
    assert "default" in argv
    assert "--output" in argv and "json" in argv
    # No --proposals flag when proposals is None.
    assert "--proposals" not in argv


def test_verify_passes_proposals_file(tmp_path: Path) -> None:
    fake = _FakeRun(stdout=json.dumps(_VERIFY_PAYLOAD))
    proposals = {"proposals": [{"proposal_id": "p_x"}], "ok": True}

    captured_argv = {"argv": None}

    def _capture(argv, **kwargs):
        captured_argv["argv"] = argv
        # The temp file must exist at subprocess.run() time and the contents
        # must equal what we passed in.
        proposals_idx = argv.index("--proposals")
        proposals_path = Path(argv[proposals_idx + 1])
        assert proposals_path.exists()
        assert json.loads(proposals_path.read_text(encoding="utf-8")) == proposals
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=fake.stdout, stderr=""
        )

    with patch(
        "freecad_mcp.aieng_bridge.verification.subprocess.run", side_effect=_capture
    ):
        result = verify_cad_modifications(
            tmp_path / "x.aieng",
            aieng_cli="aieng-fake",
            proposals=proposals,
            strictness="lenient",
        )
    assert result["ok"] is True
    assert "--proposals" in captured_argv["argv"]
    assert "lenient" in captured_argv["argv"]
    # Temp file must be cleaned up after the call.
    proposals_idx = captured_argv["argv"].index("--proposals")
    proposals_path = Path(captured_argv["argv"][proposals_idx + 1])
    assert not proposals_path.exists()


def test_verify_handles_cli_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "freecad_mcp.aieng_bridge.verification._resolve_aieng_cli",
        lambda _override: None,
    )
    result = verify_cad_modifications(tmp_path / "x.aieng")
    assert result["ok"] is False
    assert any("CLI is not available" in e for e in result["errors"])


def test_verify_constants_export() -> None:
    assert "lenient" in STRICTNESS_MODES
    assert "default" in STRICTNESS_MODES
    assert "strict" in STRICTNESS_MODES
