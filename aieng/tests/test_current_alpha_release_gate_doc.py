from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "release" / "current_alpha_release_gate.md"


def test_current_alpha_release_gate_keeps_owner_actions_explicit() -> None:
    text = DOC.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "owner-action gate" in lowered
    assert "not an automatic release" in lowered
    assert "do not infer completion from green ci alone" in lowered
    assert "testpypi" in lowered
    assert "pypi" in lowered
    assert "embedding-depth baseline" in lowered


def test_current_alpha_release_gate_preserves_honesty_boundary() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "does not certify engineering correctness" in text
    assert "solver validity" in text
    assert "cad" in text
    assert "modeling quality" in text
    assert "installable" in text
    assert "auditable" in text
    assert "externally dogfoodable" in text
