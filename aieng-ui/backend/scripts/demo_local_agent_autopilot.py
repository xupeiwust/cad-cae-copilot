from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request


def _request(api_url: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {path}: {body}") from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        raise SystemExit(f"Could not reach {api_url.rstrip('/')}{path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Local Agent Autopilot demo.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--project-id", default="demo_autopilot")
    parser.add_argument("--approve", action="store_true", help="Continue past the approval checkpoint in dry-run mode.")
    args = parser.parse_args()

    capabilities = _request(args.api_url, "/api/local-agents/capabilities")
    print("Local adapter capabilities:")
    print(json.dumps(capabilities, indent=2))

    run = _request(
        args.api_url,
        "/api/agent/autopilot/runs",
        {
            "message": "Demo: create a simple bracket and pause before CAD write.",
            "project_id": args.project_id,
            "adapter_id": "fake",
            "dry_run": True,
            "fake_actions": [
                {
                    "thought_summary": "CAD must be approval-gated.",
                    "action": {
                        "type": "tool_call",
                        "tool_name": "cad.execute_build123d",
                        "input": {
                            "project_id": args.project_id,
                            "mode": "replace",
                            "code": "from build123d import *\nbody = Box(40, 20, 6); body.label = 'demo_bracket'\nresult = body",
                        },
                    },
                    "done": False,
                    "user_message": "Approval required before writing CAD.",
                }
            ],
        },
    )
    print("\nStarted demo run:")
    print(json.dumps({
        "run_id": run["run_id"],
        "status": run["status"],
        "pending_approval": run.get("pending_approval"),
    }, indent=2))

    if run["status"] != "awaiting_approval":
        print("Expected an approval checkpoint; demo cannot continue.", file=sys.stderr)
        return 1
    if not args.approve:
        print("\nApproval checkpoint reached. Re-run with --approve to continue in dry-run mode.")
        return 0

    continued = _request(args.api_url, f"/api/agent/autopilot/runs/{run['run_id']}/continue", {"approved": True})
    print("\nAfter approval:")
    print(json.dumps({
        "run_id": continued["run_id"],
        "status": continued["status"],
        "final_message": continued.get("final_message"),
        "latest_observations": continued.get("observations", [])[-3:],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
