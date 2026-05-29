from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AutopilotToolCall(StrictModel):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


class AutopilotAskUser(StrictModel):
    type: Literal["ask_user"] = "ask_user"
    question: str = Field(min_length=1)


class AutopilotFinal(StrictModel):
    type: Literal["final"] = "final"
    message: str = Field(min_length=1)


class AutopilotPause(StrictModel):
    type: Literal["pause"] = "pause"
    reason: str = Field(min_length=1)


class AutopilotChat(StrictModel):
    type: Literal["chat"] = "chat"
    message: str = Field(min_length=1)


AutopilotAction = Annotated[
    AutopilotToolCall | AutopilotAskUser | AutopilotFinal | AutopilotPause | AutopilotChat,
    Field(discriminator="type"),
]


class AutopilotAgentAction(StrictModel):
    thought_summary: str = ""
    action: AutopilotAction
    done: bool = False
    user_message: str | None = None

    @classmethod
    def json_schema_for_adapter(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "thought_summary": {"type": "string"},
                "done": {"type": "boolean"},
                "user_message": {"type": ["string", "null"]},
                "action": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": ["tool_call", "ask_user", "final", "pause", "chat"]},
                        "tool_name": {"type": "string"},
                        "input_json": {"type": "string"},
                        "question": {"type": "string"},
                        "message": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["type", "tool_name", "input_json", "question", "message", "reason"],
                },
            },
            "required": ["thought_summary", "action", "done", "user_message"],
        }


class AutopilotObservation(StrictModel):
    id: str
    kind: Literal[
        "context",
        "tool_result",
        "tool_error",
        "policy_block",
        "approval_required",
        "agent_activity",
        "user_message",
        "final",
    ]
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class AutopilotApproval(StrictModel):
    id: str
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    level: str
    explanation: str
    created_at: str = Field(default_factory=now_iso)


class AutopilotStep(StrictModel):
    index: int
    adapter_id: str
    action: AutopilotAgentAction
    policy: dict[str, Any] | None = None
    created_at: str = Field(default_factory=now_iso)


class AutopilotRunRequest(StrictModel):
    message: str = Field(min_length=1)
    project_id: str | None = None
    session_id: str | None = None
    adapter_id: str = "fake"
    mode: Literal["assist", "autopilot", "full_agent"] = "autopilot"
    selected_geometry: dict[str, Any] = Field(default_factory=dict)
    llm_config: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    max_steps: int = Field(default=6, ge=1, le=20)
    fake_actions: list[dict[str, Any]] | None = None


class AutopilotRunState(StrictModel):
    run_id: str
    status: Literal[
        "running",
        "awaiting_approval",
        "completed",
        "failed",
        "cancelled",
        "blocked",
        "chatting",
    ]
    message: str
    project_id: str | None = None
    session_id: str | None = None
    adapter_id: str
    mode: Literal["assist", "autopilot", "full_agent"] = "autopilot"
    dry_run: bool = True
    selected_geometry: dict[str, Any] = Field(default_factory=dict)
    llm_config: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    observations: list[AutopilotObservation] = Field(default_factory=list)
    steps: list[AutopilotStep] = Field(default_factory=list)
    pending_approval: AutopilotApproval | None = None
    final_message: str | None = None
    errors: list[str] = Field(default_factory=list)


class LocalAgentCapability(StrictModel):
    adapter_id: str
    label: str
    status: Literal["available", "blocked", "missing", "error"]
    command: str
    command_path: str | None = None
    version: str | None = None
    supports_non_interactive: bool = False
    supports_json: bool = False
    supports_json_schema: bool = False
    supports_tool_disable: bool = False
    diagnostic: str = ""
    probe_duration_ms: int = 0


class AdapterInvocationResult(StrictModel):
    status: Literal["success", "error", "timeout"]
    action: AutopilotAgentAction | None = None
    raw_output: str = ""
    stderr: str = ""
    diagnostic: str = ""
    duration_ms: int = 0
