"""Release semantic-surface guard (issue #181).

The alpha honesty posture is: `.aieng` *records* evidence and context; it does
**not** certify engineering correctness and does **not** silently advance
engineering "claims". A prior one-off audit
(``aieng/docs/release/release_blocker_audit.md``) cleaned the static surfaces;
these tests pin that cleaned state so it cannot silently regress.

Scope: the *static, alpha-facing* surfaces an external agent / user actually
reads — top-level + package READMEs, the agent guides, and the canonical MCP
tool-schema descriptions. Generated/runtime artifacts are guarded separately by
``app.project_health`` and the export smoke checks; this module covers the text
that ships with the repository.

Note on matching: we look for *affirmative* prohibited phrases (e.g. "design is
certified"). Negated honesty wording ("does not certify the design", "not
production-certified") is the desired posture and is intentionally NOT matched —
the affirmative phrasings below do not occur as substrings of those negations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime_tool_schemas import TOOL_SCHEMAS

# tests/ -> backend/ -> aieng-ui/ -> workspace root
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Affirmative phrases that must never appear on an alpha-facing surface.
# Union of the lists already enforced on generated artifacts
# (app/project_health.py, tests/test_review_support_packet.py) plus the
# claim-advancement phrasings the release audit flagged.
PROHIBITED_PHRASES: tuple[str, ...] = (
    # Certification / physical-validation guarantees
    "design is certified",
    "design is validated",
    "certified safe",
    "guaranteed safe",
    "approved design",
    "engineering claim approved",
    "engineering claim accepted",
    "claim accepted",
    # Automatic claim advancement presented as a normal workflow
    "automatically advances claims",
    "claims are advanced automatically",
    "auto-advance claims",
    "automatically advance the claim",
)

# Static surfaces an external agent / user reads. Missing files are skipped so
# the guard stays robust to repo reorganisation.
_ALPHA_FACING_FILES: tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "aieng/README.md",
    "aieng-ui/README.md",
    "aieng-ui/backend/MCP_SETUP.md",
)


def _scan(text: str) -> list[str]:
    """Return the prohibited phrases present in ``text`` (case-insensitive)."""
    haystack = text.lower()
    return [phrase for phrase in PROHIBITED_PHRASES if phrase in haystack]


def _existing_alpha_files() -> list[Path]:
    return [
        path
        for rel in _ALPHA_FACING_FILES
        if (path := _REPO_ROOT / rel).is_file()
    ]


def test_alpha_facing_files_are_present() -> None:
    """At least the core READMEs/guides must resolve, else the guard is hollow."""
    found = {p.relative_to(_REPO_ROOT).as_posix() for p in _existing_alpha_files()}
    # These three are load-bearing for the alpha story and must exist.
    for required in ("README.md", "aieng/README.md", "aieng-ui/README.md"):
        assert required in found, f"alpha-facing file missing: {required}"


@pytest.mark.parametrize("doc_path", _existing_alpha_files(), ids=lambda p: p.name)
def test_static_surface_has_no_prohibited_certification_language(doc_path: Path) -> None:
    """Shipped docs must not affirmatively certify designs or advance claims."""
    hits = _scan(doc_path.read_text(encoding="utf-8"))
    rel = doc_path.relative_to(_REPO_ROOT).as_posix()
    assert not hits, (
        f"{rel} contains prohibited certification/claim-advancement wording: {hits}. "
        "Use evidence/readiness/review-required language instead (see "
        "aieng/docs/release/release_blocker_audit.md)."
    )


def test_mcp_tool_descriptions_have_no_prohibited_language() -> None:
    """The canonical MCP tool-schema descriptions external agents list must stay
    evidence-only — no certification or auto-claim-advancement wording."""
    offenders: dict[str, list[str]] = {}
    for tool_name, schema in TOOL_SCHEMAS.items():
        description = schema.get("description")
        if not isinstance(description, str):
            continue
        hits = _scan(description)
        if hits:
            offenders[tool_name] = hits
    assert not offenders, (
        f"MCP tool descriptions contain prohibited wording: {offenders}. "
        "Tool descriptions must not present certification or automatic claim "
        "advancement as a capability."
    )


def test_readmes_explain_proof_not_just_screenshots() -> None:
    english = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (_REPO_ROOT / "README.zh.md").read_text(encoding="utf-8")

    assert "## Proof, not just screenshots" in english
    assert "generated build123d source" in english
    assert "STEP/STL/GLB exports" in english
    assert "topology maps and stable `@face:*` pointers" in english
    assert "instead of trusting a static render" in english

    assert "## 不是只看截图" in chinese
    assert "生成的 build123d 源码" in chinese
    assert "STEP/STL/GLB 导出" in chinese
    assert "稳定的 `@face:*` 指针" in chinese
    assert "静态渲染图" in chinese
