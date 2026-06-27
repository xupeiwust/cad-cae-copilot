from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs" / "cad_execution_boundary.md"
README = REPO_ROOT / "README.md"


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_cad_execution_boundary_doc_exists_and_is_linked() -> None:
    assert DOC.is_file()
    assert "docs/cad_execution_boundary.md" in README.read_text(encoding="utf-8")


def test_cad_execution_boundary_explains_local_and_external_boundaries() -> None:
    text = _doc_text()

    assert "The AIENG backend itself does not require an API key" in text
    assert "The connecting MCP client or agent may use its own model provider" in text
    assert "cad.execute_build123d" in text
    assert "CalculiX" in text
    assert "approved execution creates result artifacts" in text


def test_cad_execution_boundary_pins_guardrails_without_overpromising() -> None:
    text = _doc_text()
    lower = text.lower()

    assert "approval-gated operations" in lower
    assert "reject path traversal" in lower
    assert "runtime logs redact common secret shapes" in lower
    assert "does not provide enterprise-grade sandboxing today" in lower
    assert "does not certify the physical correctness or safety" in lower

    overpromises = (
        "provides enterprise-grade sandboxing",
        "guaranteed safe",
        "risk-free sandbox",
        "certifies the physical correctness",
    )
    for phrase in overpromises:
        assert phrase not in lower


def test_cad_execution_boundary_lists_secret_shapes_and_regression_commands() -> None:
    text = _doc_text()

    for needle in ("api_key", "token", "secret", "password", "Authorization", "Bearer", "sk-"):
        assert needle in text
    assert "test_backend_logging.py" in text
    assert "forbidden_path" in text
