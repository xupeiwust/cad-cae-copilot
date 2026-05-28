from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_autopilot.claude_code_adapter import ClaudeCodeAdapter
from app.agent_autopilot.schema import AutopilotAgentAction


def main() -> int:
    adapter = ClaudeCodeAdapter()
    result = adapter.invoke(
        prompt=(
            "Return a Local Agent Autopilot final action JSON only. "
            "Use message: smoke ok."
        ),
        action_schema=AutopilotAgentAction.json_schema_for_adapter(),
        timeout_seconds=60,
    )
    print(json.dumps(result.model_dump(), indent=2))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
