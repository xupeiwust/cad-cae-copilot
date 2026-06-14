"""Multi-sample consistency gate for LLM-judged steps (#220).

Borrowed from semantic-entropy / multi-sample UQ (arXiv 2510.12040): an LLM's
*self-reported* confidence is poorly calibrated, but the *consistency* of its
answer across independent samples predicts failure far better. When several
samples of a judged decision disagree, the honest move is to ask the user
rather than act on a coin-flip.

This module is pure and provider-agnostic: it scores a list of decision
*signatures* (e.g. the proposed tool sequence) and decides whether the modal
decision is consistent enough to act on. The engine supplies the samples; the
gate never calls an LLM itself.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

DEFAULT_THRESHOLD = 0.6
_MAX_SAMPLES = 7  # cost cap — more samples rarely change the verdict
_NONE_SIGNATURE = "__none__"


def consistency_samples(llm_config: Any, *, default: int = 1) -> int:
    """How many times to sample the judged step. ``1`` disables the gate.

    Deterministic bypass: replay/fake runs always return ``1`` so tests and
    replay harnesses never fan out into multiple (non-deterministic) samples.
    The value is clamped to ``[1, _MAX_SAMPLES]``.
    """
    if not isinstance(llm_config, dict):
        return 1
    if (
        llm_config.get("replay")
        or llm_config.get("fake")
        or str(llm_config.get("provider") or "").strip().lower() in {"fake", "replay"}
    ):
        return 1
    try:
        n = int(llm_config.get("consistency_samples", default))
    except (TypeError, ValueError):
        return 1
    return max(1, min(n, _MAX_SAMPLES))


def consistency_threshold(llm_config: Any, *, default: float = DEFAULT_THRESHOLD) -> float:
    """Modal-agreement fraction required to act. Clamped to ``[0, 1]``."""
    if not isinstance(llm_config, dict):
        return default
    try:
        t = float(llm_config.get("consistency_threshold", default))
    except (TypeError, ValueError):
        return default
    return max(0.0, min(t, 1.0))


def plan_decision_signature(steps: list[dict[str, Any]] | None) -> str:
    """Reduce a plan to the decision being judged: its ordered tool sequence.

    Two samples are "the same decision" when they propose the same tools in the
    same order. An empty plan collapses to a sentinel so "do nothing" is itself
    a comparable decision.
    """
    tools: list[str] = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        name = str(step.get("tool_name") or step.get("name") or "").strip()
        if name:
            tools.append(name)
    return "|".join(tools) if tools else _NONE_SIGNATURE


def evaluate_consistency(
    signatures: list[str], *, threshold: float = DEFAULT_THRESHOLD
) -> dict[str, Any]:
    """Score modal agreement across decision signatures. Pure and total.

    Returns ``{n_samples, modal_signature, modal_count, agreement, consistent,
    distinct, distribution, threshold}``. With zero samples the result is
    ``consistent=False`` (nothing to act on). A single sample is trivially
    consistent (agreement 1.0) — the gate only bites when ``n_samples > 1``.
    """
    clean = [s for s in signatures if isinstance(s, str)]
    n = len(clean)
    if n == 0:
        return {
            "n_samples": 0,
            "modal_signature": None,
            "modal_count": 0,
            "agreement": 0.0,
            "consistent": False,
            "distinct": 0,
            "distribution": {},
            "threshold": threshold,
        }
    counts = Counter(clean)
    modal_signature, modal_count = counts.most_common(1)[0]
    agreement = modal_count / n
    return {
        "n_samples": n,
        "modal_signature": modal_signature,
        "modal_count": modal_count,
        "agreement": round(agreement, 6),
        "consistent": agreement >= threshold,
        "distinct": len(counts),
        "distribution": dict(counts),
        "threshold": threshold,
    }


def low_consistency_reply(verdict: dict[str, Any]) -> str:
    """A user-facing clarification message for an inconsistent judged step."""
    n = verdict.get("n_samples", 0)
    distinct = verdict.get("distinct", 0)
    agreement = verdict.get("agreement", 0.0)
    return (
        f"I'm not confident about the next step: {distinct} different plans across "
        f"{n} samples (top plan agreed {round(float(agreement) * 100)}% of the time, "
        f"below the {round(float(verdict.get('threshold', DEFAULT_THRESHOLD)) * 100)}% bar). "
        "Rather than act on a guess, could you clarify what you'd like me to do?"
    )
