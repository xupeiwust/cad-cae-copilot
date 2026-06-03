"""Natural-language intent resolution for the composer.

The composer already routes explicit slash commands (``/build``, ``/modify``,
``/critique``, ``/explain``, ``/simulate``) deterministically. This module is the
*front door* for everything else: it turns a plain-language message into the same
normalized intent shape those commands produce, so the existing routing + guard
machinery in ``engine.py`` can be reused verbatim — "point and shoot" without the
user having to learn the slash vocabulary.

Design (see AGENTS.md "Composer slash commands"):

* ``INTENT_REGISTRY`` is the single source of truth for routed-command semantics
  (intent_type, mutation-required / read-only / simulation, fallback trigger
  terms). ``engine.py`` derives its command sets/labels from it.
* ``resolve_intent`` is a three-tier resolver: an explicit command always wins;
  otherwise an optional (app-wired, LLM-backed) ``classifier`` runs; otherwise a
  deterministic keyword heuristic. Every tier returns an ``IntentResolution``.
* Honesty / "ask before guessing": when the resolved command is actionable but
  low-confidence or flagged ambiguous, ``needs_clarification`` is set so the
  engine biases the agent toward ``ask_user`` instead of routing on a guess.

The resolver never relaxes a guard. It only *proposes* a command; the
deterministic guards in ``engine.py`` remain the safety net.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# --- Intent registry --------------------------------------------------------
# One entry per routed command. Adding a new intent means adding one row here
# (plus, if it needs prompt bias, an instruction string in engine.py keyed by
# command) — not editing several scattered frozensets.


@dataclass(frozen=True)
class IntentSpec:
    """Static semantics of one routed command."""

    command: str
    intent_type: str
    mutation_required: bool = False
    read_only: bool = False
    simulation: bool = False
    # Lowercased substrings that, in free text, map to this command via the
    # deterministic keyword fallback (used when no LLM classifier is wired).
    trigger_terms: tuple[str, ...] = ()


INTENT_REGISTRY: dict[str, IntentSpec] = {
    "build": IntentSpec(
        command="build",
        intent_type="create_geometry",
        mutation_required=True,
        trigger_terms=("创建", "生成", "画", "建模", "create", "generate", "build", "draw"),
    ),
    "modify": IntentSpec(
        command="modify",
        intent_type="modify_geometry",
        mutation_required=True,
        trigger_terms=(
            "修改", "改成", "加", "删除", "替换", "变成", "优化外形",
            "modify", "change", "add", "remove", "replace", "make it", "turn into",
        ),
    ),
    "critique": IntentSpec(
        command="critique",
        intent_type="critique_geometry",
        read_only=True,
        trigger_terms=("点评", "评审", "审查", "可制造性", "critique", "review", "manufacturab"),
    ),
    "explain": IntentSpec(
        command="explain",
        intent_type="explain_project",
        read_only=True,
        trigger_terms=("解释", "说明", "讲解", "是什么", "explain", "describe", "what is", "tell me about"),
    ),
    "simulate": IntentSpec(
        command="simulate",
        intent_type="plan_simulation",
        simulation=True,
        trigger_terms=("仿真", "模拟", "受力", "应力", "载荷", "simulate", "simulation", "fea", "stress", "load case"),
    ),
}


# Below this confidence (or when explicitly flagged ambiguous), an actionable
# resolved command triggers a clarification bias rather than direct routing.
CONFIDENCE_CLARIFY_THRESHOLD = 0.45


def registry_commands() -> frozenset[str]:
    return frozenset(INTENT_REGISTRY)


def commands_where(predicate: Callable[[IntentSpec], bool]) -> frozenset[str]:
    return frozenset(c for c, spec in INTENT_REGISTRY.items() if predicate(spec))


def intent_labels() -> dict[str, str]:
    return {c: spec.intent_type for c, spec in INTENT_REGISTRY.items()}


# --- Resolution result ------------------------------------------------------


@dataclass
class IntentResolution:
    """Normalized intent for one message.

    ``command`` is ``None`` when no actionable command was detected — the engine
    then leaves the run as free natural language (current behavior). When a
    command is present it is always a key of ``INTENT_REGISTRY``.
    """

    command: Optional[str]
    intent_type: Optional[str]
    confidence: float
    source: str  # explicit_command | llm_classifier | keyword_heuristic | none
    ambiguous: bool = False
    needs_clarification: bool = False
    targets: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "intent_type": self.intent_type,
            "confidence": round(float(self.confidence), 3),
            "source": self.source,
            "ambiguous": bool(self.ambiguous),
            "needs_clarification": bool(self.needs_clarification),
            "targets": list(self.targets),
            "parameters": dict(self.parameters),
            "reason": self.reason,
        }


def _none_resolution(source: str, reason: str) -> IntentResolution:
    return IntentResolution(
        command=None,
        intent_type=None,
        confidence=0.0,
        source=source,
        reason=reason,
    )


# Classifier contract: (message, context) -> IntentResolution | None.
# Returning None means "could not classify" and resolution falls through to the
# keyword heuristic. ``context`` may carry ``llm_config`` and a compact project
# summary; classifiers must be robust to either being absent.
IntentClassifier = Callable[[str, dict[str, Any]], Optional[IntentResolution]]


# --- Tier 3: deterministic keyword heuristic --------------------------------


def keyword_classify(message: str) -> IntentResolution:
    """Deterministic substring classifier — the always-available fallback.

    Modify is checked before build (mirrors the legacy ``_geometry_mutation_intent``
    precedence). Read-only / simulation terms only match when no mutation term is
    present, so "add a load case and simulate" still reads as a modify (mutation)
    rather than being silently downgraded to a read-only plan. Confidence is
    modest (the match is shallow), but above the clarify threshold so behavior is
    unchanged from today's keyword routing — no surprise clarification prompts.
    """
    text = str(message or "").lower()
    if not text.strip():
        return _none_resolution("keyword_heuristic", "empty message")

    # Mutation intents take precedence (a request that both adds geometry and
    # mentions simulation is still a geometry edit first).
    for command in ("modify", "build"):
        spec = INTENT_REGISTRY[command]
        hit = next((t for t in spec.trigger_terms if t in text), None)
        if hit:
            return IntentResolution(
                command=command,
                intent_type=spec.intent_type,
                confidence=0.6,
                source="keyword_heuristic",
                reason=f"matched {command} term {hit!r}",
            )

    for command in ("simulate", "critique", "explain"):
        spec = INTENT_REGISTRY[command]
        hit = next((t for t in spec.trigger_terms if t in text), None)
        if hit:
            return IntentResolution(
                command=command,
                intent_type=spec.intent_type,
                confidence=0.55,
                source="keyword_heuristic",
                reason=f"matched {command} term {hit!r}",
            )

    return _none_resolution("keyword_heuristic", "no trigger term matched")


# --- Resolver ---------------------------------------------------------------


def _normalize_command(value: Any) -> Optional[str]:
    if isinstance(value, str) and value in INTENT_REGISTRY:
        return value
    return None


def _apply_clarification_gate(res: IntentResolution) -> IntentResolution:
    """Mark a resolution as needing clarification when it is actionable but weak.

    No command → nothing to clarify (the run proceeds as free natural language).
    A command below the confidence threshold, or explicitly flagged ambiguous,
    sets ``needs_clarification`` so the engine biases toward ``ask_user``.
    """
    if res.command is None:
        res.needs_clarification = False
        return res
    if res.ambiguous or res.confidence < CONFIDENCE_CLARIFY_THRESHOLD:
        res.needs_clarification = True
    return res


def _sanitize_classifier_result(res: IntentResolution) -> IntentResolution:
    """Trust-but-verify an external classifier's output against the registry."""
    command = _normalize_command(res.command)
    if command is None:
        return _none_resolution(
            res.source or "llm_classifier",
            res.reason or "classifier returned no valid command",
        )
    spec = INTENT_REGISTRY[command]
    # The registry owns intent_type — never let a classifier desync it.
    res.command = command
    res.intent_type = spec.intent_type
    try:
        res.confidence = max(0.0, min(1.0, float(res.confidence)))
    except (TypeError, ValueError):
        res.confidence = 0.5
    if not isinstance(res.targets, list):
        res.targets = []
    if not isinstance(res.parameters, dict):
        res.parameters = {}
    return res


def resolve_intent(
    message: str,
    *,
    existing_command: Any = None,
    classifier: Optional[IntentClassifier] = None,
    context: Optional[dict[str, Any]] = None,
) -> IntentResolution:
    """Resolve a message into a normalized intent.

    Tier 1 — an explicit composer command always wins (confidence 1.0).
    Tier 2 — an optional LLM classifier (app-wired); failures fall through.
    Tier 3 — the deterministic keyword heuristic.

    The clarification gate is applied to tiers 2 and 3 (an explicit command is
    never ambiguous). The function never raises on a misbehaving classifier.
    """
    explicit = _normalize_command(existing_command)
    if explicit is not None:
        spec = INTENT_REGISTRY[explicit]
        return IntentResolution(
            command=explicit,
            intent_type=spec.intent_type,
            confidence=1.0,
            source="explicit_command",
            reason="explicit /command",
        )

    if classifier is not None:
        try:
            result = classifier(message, context or {})
        except Exception:  # a classifier must never break a run
            result = None
        if result is not None:
            sanitized = _sanitize_classifier_result(result)
            # A valid command is used; an abstaining / malformed result (no valid
            # command) falls through to the deterministic keyword tier rather than
            # dead-ending at "no intent".
            if sanitized.command is not None:
                return _apply_clarification_gate(sanitized)

    return _apply_clarification_gate(keyword_classify(message))


# --- Tier 2 factory: LLM-backed classifier ----------------------------------

_CLASSIFIER_SYSTEM_PROMPT = (
    "You classify a CAD/CAE engineering-assistant user message into exactly one "
    "intent. Reply with ONLY a JSON object, no prose, no code fences. Schema:\n"
    '{"command": one of '
    '["build","modify","critique","explain","simulate",null], '
    '"confidence": 0..1, "ambiguous": bool, '
    '"targets": [string], "parameters": {string: any}, "reason": string}\n'
    "Meaning of each command:\n"
    "- build: create NEW CAD geometry from scratch.\n"
    "- modify: change/add/remove features on the EXISTING CAD model.\n"
    "- critique: read-only manufacturability / design review of geometry.\n"
    "- explain: read-only explanation of the project/model/results.\n"
    "- simulate: set up or plan a structural simulation (FEA) — never auto-runs.\n"
    "Use command=null when the message is small talk, a question about the tool "
    "itself, or genuinely has no engineering intent. Set ambiguous=true (and a "
    "lower confidence) when two intents are equally plausible. Put referenced "
    "part/artifact names in targets and any concrete dimensions/materials/loads "
    "in parameters. Do not invent targets."
)


def parse_classifier_json(raw: str) -> Optional[IntentResolution]:
    """Parse a classifier model's raw text into an IntentResolution, or None.

    Tolerant of surrounding prose / code fences. Returns None on anything it
    cannot turn into a valid registry command (so resolution falls back).
    """
    import json
    import re

    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    # Strip ``` fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    # Grab the first {...} block if there is extra prose around it.
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        text = match.group(0)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    command = _normalize_command(data.get("command"))
    if command is None:
        return _none_resolution("llm_classifier", str(data.get("reason") or "no command"))
    spec = INTENT_REGISTRY[command]
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    targets = data.get("targets")
    parameters = data.get("parameters")
    return IntentResolution(
        command=command,
        intent_type=spec.intent_type,
        confidence=confidence,
        source="llm_classifier",
        ambiguous=bool(data.get("ambiguous", False)),
        targets=[str(t) for t in targets] if isinstance(targets, list) else [],
        parameters=parameters if isinstance(parameters, dict) else {},
        reason=str(data.get("reason") or ""),
    )


def build_llm_intent_classifier(
    provider_factory: Callable[[Any, dict[str, Any]], Any],
    settings: Any,
    *,
    timeout_seconds: float = 6.0,
) -> IntentClassifier:
    """Build an LLM-backed classifier closure (app-wired).

    The provider is built lazily per call from ``context["llm_config"]`` (intent
    is request-scoped) using the shared ``provider_factory``. Any failure —
    missing config, no API key, timeout, unparseable output — returns ``None`` so
    ``resolve_intent`` falls back to the deterministic keyword heuristic. This
    keeps the live path safe and the test path deterministic.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

    def _classify(message: str, context: dict[str, Any]) -> Optional[IntentResolution]:
        llm_config = (context or {}).get("llm_config")
        if not isinstance(llm_config, dict) or not llm_config:
            return None
        # No key configured → don't attempt a call; fall back silently.
        if not (llm_config.get("api_key") or llm_config.get("api_key_env")):
            return None
        try:
            provider = provider_factory(settings, llm_config)
        except Exception:
            return None

        project_hint = ""
        summary = (context or {}).get("project_summary")
        if isinstance(summary, dict):
            cad = summary.get("cad") if isinstance(summary.get("cad"), dict) else {}
            has_geometry = bool(cad.get("known_geometry") or cad.get("status"))
            project_hint = (
                f"\n\nProject context: a CAD model {'already exists' if has_geometry else 'does NOT exist yet'}."
            )
        user_prompt = f"User message:\n{message}{project_hint}"

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    provider.generate,
                    system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                )
                raw = future.result(timeout=timeout_seconds)
        except (FutureTimeoutError, Exception):
            return None
        return parse_classifier_json(raw)

    return _classify
