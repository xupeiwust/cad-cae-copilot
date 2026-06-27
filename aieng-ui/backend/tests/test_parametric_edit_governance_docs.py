from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs" / "parametric-edit-governance.md"
README = REPO_ROOT / "README.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_parametric_edit_governance_doc_exists_and_is_linked() -> None:
    assert DOC.is_file()
    assert "docs/parametric-edit-governance.md" in README.read_text(encoding="utf-8")


def test_parametric_edit_governance_requires_structured_proposal_fields() -> None:
    text = _text()

    for needle in (
        "target `featureId`",
        "target `parameterName`",
        "cad_parameter_name",
        "old value and proposed new value",
        "scope (`local`, `global`, or `unscoped`)",
        "protected-feature or design-target risk notes",
    ):
        assert needle in text


def test_parametric_edit_governance_preserves_audit_restore_and_stale_boundaries() -> None:
    text = _text()

    assert "state/last_edit_diff.json" in text
    assert "package snapshot" in text
    assert "downstream CAE/revalidation artifacts are marked stale" in text
    assert "cad.restore_snapshot" in text
    assert "Rejected or failed parameter edits must preserve the previous package state" in text
    assert "explicit scope-risk confirmation" in text


def test_parametric_edit_governance_does_not_overclaim_edit_support() -> None:
    text = _text()
    lower = text.lower()

    assert "do not claim parametric edit support" in lower
    assert "not automatically editable through" in lower
    assert "do not make arbitrary python macro generation the default" in lower
    assert "do not treat a proposal as evidence" in lower

    for prohibited in (
        "approved design",
        "certified safe",
        "automatically accepted",
    ):
        assert prohibited not in lower
