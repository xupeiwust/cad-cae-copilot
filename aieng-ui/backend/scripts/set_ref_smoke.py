"""Smoke-test cad.set_reference_image without going through MCP.

The MCP client caches its tool list at connection time, so a newly-registered
MCP tool isn't visible until the client reconnects. This script bypasses that
by importing the public function directly and invoking it against the same
runtime settings the MCP server uses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend to path so `app.*` imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cad_generation import set_reference_image
from app.config import Settings


def main(project_id: str, image_url: str, description: str = "") -> None:
    settings = Settings.from_env()
    result = set_reference_image(
        settings,
        project_id,
        {"image_url": image_url, "description": description},
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: set_ref_smoke.py <project_id> <image_url> [description]")
        sys.exit(2)
    proj = sys.argv[1]
    url = sys.argv[2]
    desc = sys.argv[3] if len(sys.argv) > 3 else ""
    main(proj, url, desc)
