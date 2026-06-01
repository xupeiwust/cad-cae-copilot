from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from .schema import AutopilotObservation


@dataclass(frozen=True)
class ObservationImportance:
    """Semantic importance ranking for observations.

    Immutable so that compression decisions are deterministic and reproducible.
    """

    level: Literal["critical", "high", "medium", "low", "fleeting"]
    tags: tuple[str, ...] = ()

    @classmethod
    def from_observation(cls, obs: AutopilotObservation | dict[str, Any]) -> "ObservationImportance":
        """Infer importance from observation kind and content."""
        if isinstance(obs, AutopilotObservation):
            kind = obs.kind
            data = obs.data
        else:
            kind = obs.get("kind", "unknown")
            data = obs.get("data", {})

        if kind == "user_message":
            return cls("critical", ("user_intent",))
        elif kind == "tool_error":
            return cls("high", ("error",))
        elif kind == "policy_block":
            return cls("high", ("blocker",))
        elif kind == "tool_result":
            tool_name = data.get("tool_name", "") if isinstance(data, dict) else ""
            if tool_name == "cad.plan_build123d_skill":
                return cls("high", ("cad", "skill_plan"))
            if tool_name in ("cad.execute_build123d", "cad.critique"):
                return cls("high", ("cad", "geometry"))
            elif tool_name in ("cae.run_solver",):
                return cls("high", ("cae", "simulation"))
            elif tool_name in ("cad.edit_parameter", "cad.replace_part", "cad.remove_part"):
                return cls("high", ("cad", "mutation"))
            elif tool_name in ("aieng.agent_context", "aieng.inspect_package"):
                return cls("high", ("context",))
            return cls("medium", ("tool_result",))
        elif kind == "approval_required":
            return cls("medium", ("approval",))
        elif kind == "agent_activity":
            return cls("low", ("meta",))
        elif kind == "final":
            return cls("critical", ("completion",))
        else:
            return cls("medium", (kind,))


@dataclass
class MemoryLayerConfig:
    """Configurable memory layer limits.

    All token counts are rough estimates (chars / 4). Real token counts
    depend on the tokenizer, but this is accurate enough for budget
    management.
    """

    working_max_count: int = 5
    working_max_tokens: int = 6000
    archive_max_tokens: int = 1500
    system_max_tokens: int = 4000


@dataclass
class _WorkingEntry:
    """Internal representation of an observation in the working layer."""

    observation: dict[str, Any]
    importance: ObservationImportance
    index: int  # monotonic insertion order


class ContextMemoryManager:
    """Hierarchical context memory manager for agent loops.

    Manages observations across four conceptual layers:
    - System:  immutable content (rules, tools, schema)
    - Archive: compressed history (one-line digests of old observations)
    - Working: recent observations with full detail
    - Incremental: the current step's new observation

    Solves prompt bloat by:
    1. Never re-transmitting system content on every step
    2. Compressing old observations into a digest chain instead of
       retaining full detail indefinitely
    3. Prioritizing semantic importance over naive time-based truncation
    4. Supporting incremental transmission for session-aware adapters
    """

    def __init__(
        self,
        system_content: dict[str, Any],
        config: MemoryLayerConfig | None = None,
    ) -> None:
        self.system_content = system_content
        self.config = config or MemoryLayerConfig()
        self._working: list[_WorkingEntry] = []
        self._archive: str = ""
        self._seen_count: int = 0
        self._compressed_count: int = 0

    # -- Public write API --

    def add_observation(self, obs: AutopilotObservation | dict[str, Any]) -> None:
        """Add a single observation and trigger compression if needed."""
        if isinstance(obs, AutopilotObservation):
            obs_dict = obs.model_dump()
        else:
            obs_dict = dict(obs)

        self._seen_count += 1
        entry = _WorkingEntry(
            observation=obs_dict,
            importance=ObservationImportance.from_observation(obs),
            index=self._seen_count,
        )
        self._working.append(entry)
        self._maybe_compress()

    def add_observations(self, observations: list[AutopilotObservation | dict[str, Any]]) -> None:
        """Batch-add observations (e.g. during engine bootstrap).

        More efficient than calling add_observation() in a loop because
        compression only runs once at the end.
        """
        for obs in observations:
            if isinstance(obs, AutopilotObservation):
                obs_dict = obs.model_dump()
            else:
                obs_dict = dict(obs)

            self._seen_count += 1
            entry = _WorkingEntry(
                observation=obs_dict,
                importance=ObservationImportance.from_observation(obs),
                index=self._seen_count,
            )
            self._working.append(entry)
        self._maybe_compress()

    def reset_working_memory(self) -> None:
        """Clear the working layer while preserving the archive.

        Useful when the user explicitly asks to forget recent context
        (e.g. "start over" or "forget what we just did").
        """
        for entry in self._working:
            self._compress_one_to_archive(entry)
        self._working.clear()

    # -- Public read API --

    @property
    def seen_count(self) -> int:
        """Total number of observations that have been added."""
        return self._seen_count

    def build_full_prompt(
        self,
        objective: str,
        *,
        project_id: str | None = None,
        selected_geometry: dict[str, Any] | None = None,
        agent_context: dict[str, Any] | None = None,
        working_state: dict[str, Any] | None = None,
    ) -> str:
        """Build a full hierarchical prompt.

        Use this for:
        - First step initialization
        - Adapters that do NOT support session continuation
        - Reconnection / recovery after a disconnect
        """
        payload: dict[str, Any] = {
            "objective": objective,
            "system_context": self.system_content,
            "archive_digest": self._archive or "No prior history.",
            "working_state": working_state or {},
            "working_memory": self._build_working_layer_payload(),
        }
        if project_id is not None:
            payload["active_project_id"] = project_id
        if selected_geometry:
            payload["selected_geometry"] = selected_geometry
        if agent_context:
            payload["agent_context"] = agent_context

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def build_incremental_prompt(
        self,
        objective: str,
        new_observation: AutopilotObservation | dict[str, Any] | None = None,
        instruction: str = "Continue based on working memory and this new observation.",
    ) -> str:
        """Build an incremental prompt for session-aware adapters.

        Only contains: objective + new observation + instruction.
        The adapter is expected to have the system + working + archive
        context already loaded in its session state.
        """
        payload: dict[str, Any] = {
            "objective": objective,
            "instruction": instruction,
        }
        if new_observation is not None:
            payload["new_observation"] = self._compact_single_observation(new_observation)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def build_resume_prompt(
        self,
        objective: str,
        *,
        working_state: dict[str, Any] | None = None,
        current_plan_step: dict[str, Any] | None = None,
        latest_observation: AutopilotObservation | dict[str, Any] | None = None,
        pending_approval: dict[str, Any] | None = None,
        instruction: str = "Resume the run from this compact state. Do not re-ask questions already answered in accepted_assumptions.",
    ) -> str:
        payload: dict[str, Any] = {
            "objective": objective,
            "instruction": instruction,
            "system_context": self.system_content,
            "archive_digest": self._archive or "No prior history.",
            "resume_summary": {
                "working_state": working_state or {},
                "current_plan_step": current_plan_step,
                "pending_approval": pending_approval,
            },
        }
        if latest_observation is not None:
            payload["resume_summary"]["latest_observation"] = self._compact_single_observation(latest_observation)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def get_memory_stats(self) -> dict[str, Any]:
        """Return debugging / monitoring statistics."""
        working_tokens = sum(
            self._estimate_tokens(self._compact_working_entry(e)) for e in self._working
        )
        archive_tokens = len(self._archive) // 4
        system_tokens = self._estimate_tokens(self.system_content)

        # Rough "what if we kept everything" baseline
        full_baseline = system_tokens + working_tokens + archive_tokens + (self._compressed_count * 500)

        compression_ratio = 0.0
        if full_baseline > 0:
            compressed = system_tokens + working_tokens + archive_tokens
            compression_ratio = 1.0 - (compressed / full_baseline)

        return {
            "total_seen": self._seen_count,
            "working_count": len(self._working),
            "working_tokens": working_tokens,
            "archive_tokens": archive_tokens,
            "system_tokens": system_tokens,
            "compressed_count": self._compressed_count,
            "compression_ratio": round(compression_ratio, 2),
        }

    # -- Internal compression --

    def _maybe_compress(self) -> None:
        """Compress working layer when it exceeds budget.

        Compression strategy:
        1. Count limit exceeded  -> compress lowest-importance entry
        2. Token limit exceeded  -> compress lowest-importance entry
        3. Only 2 entries left but still over limit -> in-place truncate oldest

        Low-importance entries are evicted first so that critical/high
        observations (user messages, tool errors, CAD results) stay in
        working memory longer.
        """
        # Phase 1: count-based eviction
        while len(self._working) > self.config.working_max_count:
            idx = self._pick_lowest_importance_index()
            entry = self._working.pop(idx)
            self._compress_one_to_archive(entry)

        # Phase 2: token-based eviction
        while True:
            working_tokens = sum(
                self._estimate_tokens(self._compact_working_entry(e)) for e in self._working
            )
            if working_tokens <= self.config.working_max_tokens:
                break
            if len(self._working) <= 2:
                # In-place truncate the oldest entry instead of removing it
                self._in_place_truncate_oldest()
                break
            idx = self._pick_lowest_importance_index()
            entry = self._working.pop(idx)
            self._compress_one_to_archive(entry)

    def _pick_lowest_importance_index(self) -> int:
        """Return the index of the working entry with the lowest importance.

        Importance ranking: low < medium < high < critical.
        If all entries have the same importance, return 0 (oldest).
        """
        if not self._working:
            return 0
        priority = {"fleeting": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        min_priority = float("inf")
        min_idx = 0
        for idx, entry in enumerate(self._working):
            p = priority.get(entry.importance.level, 2)
            if p < min_priority:
                min_priority = p
                min_idx = idx
        return min_idx

    def _compress_one_to_archive(self, entry: _WorkingEntry) -> None:
        """Compress a single working entry into a one-line archive digest."""
        summary = self._summarize_entry(entry)
        if self._archive:
            self._archive += f" | {summary}"
        else:
            self._archive = summary

        self._compressed_count += 1

        # If archive exceeds budget, fold the middle
        if len(self._archive) // 4 > self.config.archive_max_tokens:
            self._fold_archive()

    def _summarize_entry(self, entry: _WorkingEntry) -> str:
        """Create a one-line summary of a working entry."""
        obs = entry.observation
        kind = obs.get("kind", "unknown")
        summary = str(obs.get("summary", ""))

        if kind == "tool_result":
            data = obs.get("data", {})
            tool_name = data.get("tool_name", "unknown") if isinstance(data, dict) else "unknown"
            output = data.get("output", {}) if isinstance(data, dict) else {}
            if isinstance(output, dict):
                if "named_parts" in output:
                    parts = output.get("named_parts", [])
                    return f"[{tool_name}] {len(parts)} part(s) -- {summary[:60]}"
                if "verdict" in output:
                    return f"[{tool_name}] verdict={output.get('verdict')} -- {summary[:50]}"
            return f"[{tool_name}] {summary[:80]}"
        elif kind == "tool_error":
            return f"[ERROR] {summary[:80]}"
        elif kind == "user_message":
            return f"[User] {summary[:80]}"
        elif kind == "policy_block":
            return f"[Blocked] {summary[:60]}"
        elif kind == "approval_required":
            data = obs.get("data", {})
            tool_name = data.get("tool_name", "?") if isinstance(data, dict) else "?"
            return f"[Approval] {tool_name} -- {summary[:60]}"
        else:
            return f"[{kind}] {summary[:80]}"

    def _fold_archive(self) -> None:
        """Fold the middle of an over-long archive chain and enforce char budget."""
        parts = self._archive.split(" | ")
        if len(parts) <= 6:
            self._archive = " | ".join(parts[:6])
        else:
            # Keep first 2 and last 3, fold middle
            kept = parts[:2] + ["..."] + parts[-3:]
            self._archive = " | ".join(kept)

        # Hard cap on total characters (reserve room for truncation marker)
        max_chars = self.config.archive_max_tokens * 4
        suffix = "...[truncated]"
        if len(self._archive) > max_chars:
            truncate_to = max(0, max_chars - len(suffix))
            self._archive = self._archive[:truncate_to] + suffix

    def _in_place_truncate_oldest(self) -> None:
        """Truncate the oldest working entry in place (do not remove it)."""
        if not self._working:
            return
        oldest = self._working[0]
        compact = self._compact_working_entry(oldest)
        # Force a very small representation
        truncated = {
            "kind": compact.get("kind"),
            "summary": str(compact.get("summary", ""))[:100],
        }
        oldest.observation.update(truncated)

    def _build_working_layer_payload(self) -> list[dict[str, Any]]:
        """Convert working entries to prompt-ready dicts."""
        return [self._compact_working_entry(e) for e in self._working]

    def _compact_working_entry(self, entry: _WorkingEntry) -> dict[str, Any]:
        """Compact a working entry based on its importance."""
        obs = entry.observation
        importance = entry.importance.level

        result: dict[str, Any] = {
            "kind": obs.get("kind"),
        }

        if importance in ("critical", "high"):
            # Keep full summary + compacted data
            result["summary"] = str(obs.get("summary", ""))[:800]
            data = obs.get("data")
            if data:
                result["data"] = self._compact_observation_data(data)
        elif importance == "medium":
            # Keep summary + key fields only
            result["summary"] = str(obs.get("summary", ""))[:400]
            data = obs.get("data")
            if isinstance(data, dict):
                result["data"] = {
                    k: v for k, v in data.items() if k in ("tool_name", "input", "policy")
                }
        else:
            # Low / fleeting: summary only
            result["summary"] = str(obs.get("summary", ""))[:200]

        return result

    def _compact_single_observation(
        self,
        observation: AutopilotObservation | dict[str, Any],
    ) -> dict[str, Any]:
        """Compact a single observation for incremental prompts."""
        if isinstance(observation, AutopilotObservation):
            obs_dict = observation.model_dump()
        else:
            obs_dict = dict(observation)

        importance = ObservationImportance.from_observation(observation)
        entry = _WorkingEntry(
            observation=obs_dict,
            importance=importance,
            index=0,
        )
        return self._compact_working_entry(entry)

    def _compact_observation_data(self, data: Any) -> Any:
        """Compact observation data with domain-aware rules."""
        if not isinstance(data, dict):
            text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
            if len(text) > 2000:
                return {"summary": text[:2000] + f"...[truncated {len(text) - 2000} chars]"}
            return data

        # Domain-aware compaction for known tool outputs
        output = data.get("output")
        tool_name = data.get("tool_name", "")

        if data.get("error_class") == "cad_build_error" or (
            tool_name == "cad.execute_build123d" and data.get("error")
        ):
            return self._compact_cad_build_error(data)

        if isinstance(output, dict):
            if output.get("skill_name") == "cad.plan_build123d_skill":
                proposed_input = output.get("proposed_input") if isinstance(output.get("proposed_input"), dict) else {}
                if not proposed_input:
                    proposed_input = output.get("execute_input") if isinstance(output.get("execute_input"), dict) else {}
                return {
                    "tool_name": tool_name,
                    "status": output.get("status"),
                    "skill_name": output.get("skill_name"),
                    "intent": output.get("intent"),
                    "brief": output.get("brief"),
                    "assumptions": output.get("assumptions"),
                    "warnings": output.get("warnings"),
                    "verification_targets": output.get("verification_targets") or output.get("validation_targets"),
                    "fallback_recommendation": output.get("fallback_recommendation") or output.get("recommendation"),
                    "match_confidence": output.get("match_confidence"),
                    "matched_terms": output.get("matched_terms"),
                    "rejection_reason": output.get("rejection_reason"),
                    "proposed_tool": output.get("proposed_tool") or output.get("next_tool"),
                    "proposed_input": {
                        "project_id": proposed_input.get("project_id"),
                        "name": proposed_input.get("name"),
                        "code": proposed_input.get("code"),
                        "mode": proposed_input.get("mode"),
                        "model_kind": proposed_input.get("model_kind"),
                        "timeout": proposed_input.get("timeout"),
                    } if proposed_input else None,
                }

            # agent_context output
            if "schema_version" in output and "project_id" in output:
                cad = output.get("cad", {})
                brep = output.get("brep_graph", {})
                return {
                    "tool_name": tool_name,
                    "project": (
                        output.get("project", {}).get("name")
                        if isinstance(output.get("project"), dict)
                        else None
                    ),
                    "cad_status": cad.get("status") if isinstance(cad, dict) else None,
                    "feature_count": (
                        cad.get("topology_references", {}).get("feature_count")
                        if isinstance(cad, dict)
                        else None
                    ),
                    "face_count": brep.get("face_count") if isinstance(brep, dict) else None,
                }

            # cad.critique output
            if "findings" in output or "fail_first_objections" in output:
                findings = output.get("findings", []) if isinstance(output, dict) else []
                return {
                    "tool_name": tool_name,
                    "verdict": output.get("verdict"),
                    "finding_count": len(findings),
                    "top_objections": (
                        output.get("fail_first_objections", [])[:3]
                        if isinstance(output, dict)
                        else []
                    ),
                }

        # Generic: truncate
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(text) > 2000:
            return {"summary": text[:2000] + f"...[truncated {len(text) - 2000} chars]"}
        return data

    def _compact_cad_build_error(self, data: dict[str, Any]) -> dict[str, Any]:
        error = str(data.get("error") or "")
        tool_input = data.get("input") if isinstance(data.get("input"), dict) else {}
        code = tool_input.get("code") if isinstance(tool_input, dict) else None
        top_line = self._top_traceback_line(error)
        compact: dict[str, Any] = {
            "tool_name": data.get("tool_name") or "cad.execute_build123d",
            "error_class": data.get("error_class") or "cad_build_error",
            "recoverable": data.get("recoverable", True),
            "exception_type": self._exception_type(top_line),
            "top_traceback_line": top_line,
            "failing_input": {
                "project_id": tool_input.get("project_id"),
                "name": tool_input.get("name"),
                "mode": tool_input.get("mode"),
                "model_kind": tool_input.get("model_kind"),
                "timeout": tool_input.get("timeout"),
                "code_chars": len(code) if isinstance(code, str) else 0,
            },
        }
        if isinstance(code, str) and len(code) <= 1800:
            compact["source_snippet"] = code
        elif isinstance(code, str):
            compact["source_snippet"] = code[:1800] + f"...[truncated {len(code) - 1800} chars]"
        return compact

    @staticmethod
    def _top_traceback_line(error: str) -> str:
        lines = [line.strip() for line in error.splitlines() if line.strip()]
        if not lines:
            return ""
        for line in reversed(lines):
            if line.startswith("File ") or line.startswith("^") or line == "Traceback (most recent call last):":
                continue
            return line[:500]
        return lines[-1][:500]

    @staticmethod
    def _exception_type(line: str) -> str | None:
        if ":" not in line:
            return None
        candidate = line.split(":", 1)[0].strip()
        if not candidate or " " in candidate:
            return None
        if candidate.endswith(("Error", "Exception")) or "." in candidate:
            return candidate
        return None

    @staticmethod
    def _estimate_tokens(obj: Any) -> int:
        """Rough token estimate: character count / 4."""
        try:
            text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            text = str(obj)
        return max(1, len(text) // 4)
