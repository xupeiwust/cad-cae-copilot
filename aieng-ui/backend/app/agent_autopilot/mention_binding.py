"""Strict @part / @artifact mention binding (v1).

Pure and side-effect-free. Resolves ``composer_intent.mentions`` against the
available workspace/agent context and returns structured bindings so downstream
prompt/context can say whether each referenced part/artifact is known, unknown,
or unverified — instead of treating every mention as valid.

Scope: @part and @artifact only. @face / @workspace / @project are out of scope.

Honesty rule: when NO authoritative index is available for a kind, the binding
is ``known=None`` ("unverified") — never ``known=False``. ``known=False`` is
reserved for the case where we DO have an index and the value is genuinely
absent from it.
"""

from __future__ import annotations

from typing import Any

_BINDABLE_KINDS = ("part", "artifact")

# Ordered index: a list of (source_name, labels). ``None`` (or empty) means the
# binding context is unavailable for that kind.
Index = list[tuple[str, list[str]]]


def mention_status_word(known: bool | None) -> str:
    """Human word for a binding's known flag: known / not found / unverified."""
    if known is True:
        return "known"
    if known is False:
        return "not found"
    return "unverified"


def _resolve(value: str, indexes: Index | None) -> tuple[bool | None, str | None, str | None, str | None]:
    """Resolve one value against ordered (source, labels) indexes.

    Returns (known, source, canonical_id, reason).
    """
    if not indexes:  # None or [] → no authoritative context available
        return None, None, None, "no binding context available"
    # Exact match first, then case-insensitive (canonical_id keeps index casing).
    for source, labels in indexes:
        if value in labels:
            return True, source, value, None
    lowered = value.lower()
    for source, labels in indexes:
        for label in labels:
            if label.lower() == lowered:
                return True, source, label, None
    sources = ", ".join(source for source, _ in indexes) or "available context"
    return False, None, None, f"not found in {sources}"


def build_mention_bindings(
    mentions: Any,
    *,
    part_indexes: Index | None = None,
    artifact_indexes: Index | None = None,
) -> list[dict[str, Any]]:
    """Resolve @part / @artifact mentions into structured bindings. Pure.

    ``mentions`` is ``composer_intent.mentions`` (list of ``{kind, raw, value}``).
    ``part_indexes`` / ``artifact_indexes`` are ordered ``(source, labels)`` lists
    (or None when no authoritative context exists). Non-part/artifact mentions
    and malformed entries are skipped. Order is preserved.
    """
    bindings: list[dict[str, Any]] = []
    if not isinstance(mentions, list):
        return bindings
    for mention in mentions:
        if not isinstance(mention, dict):
            continue
        kind = mention.get("kind")
        if kind not in _BINDABLE_KINDS:
            continue
        value = mention.get("value")
        if not (isinstance(value, str) and value.strip()):
            continue
        raw = mention.get("raw")
        if not (isinstance(raw, str) and raw.strip()):
            raw = f"@{kind}:{value}"
        indexes = part_indexes if kind == "part" else artifact_indexes
        known, source, canonical_id, reason = _resolve(value, indexes)
        bindings.append({
            "kind": kind,
            "value": value,
            "mention": raw,
            "known": known,
            "source": source,
            "canonical_id": canonical_id,
            "reason": reason,
        })
    return bindings


def bindings_to_targets(bindings: Any) -> dict[str, list[dict[str, Any]]]:
    """Group bindings into ``{"parts": [...], "artifacts": [...]}`` target entries.

    Each entry keeps value / known / source / canonical_id / reason. Used by the
    /simulate readiness report so it does not duplicate the lookup.
    """
    parts: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for binding in bindings or []:
        if not isinstance(binding, dict):
            continue
        entry = {
            "value": binding.get("value"),
            "known": binding.get("known"),
            "source": binding.get("source"),
            "canonical_id": binding.get("canonical_id"),
            "reason": binding.get("reason"),
        }
        if binding.get("kind") == "part":
            parts.append(entry)
        elif binding.get("kind") == "artifact":
            artifacts.append(entry)
    return {"parts": parts, "artifacts": artifacts}
