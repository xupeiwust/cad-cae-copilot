from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ROOT = APP_ROOT.parent
WORKSPACE_ROOT = PLATFORM_ROOT.parent


def ensure_aieng_on_path() -> None:
    """Ensure ``aieng/src`` is on ``sys.path`` so ``from aieng.* import ...`` works.

    Centralizes the path-insertion that several modules need when they import
    the aieng core lazily (inside a function). Idempotent.
    """
    aieng_src = str(WORKSPACE_ROOT / "aieng" / "src")
    if aieng_src not in sys.path:
        sys.path.insert(0, aieng_src)

AIENG_EXT = ".aieng"
STEP_EXTENSIONS = {".step", ".stp"}
PROJECT_ID = re.compile(r"[a-f0-9]{12}")
SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
TOOLS_ALLOWED = [
    "cad_import_step",
    "cad_export_step",
    "cad_export_stl",
    "aieng_parse_patch",
    "aieng_execute_patch",
]
RUNTIME_CONFIG_FILENAME = "runtime_config.json"
SUPPORTED_TOPOLOGY_BACKENDS = {"auto", "mock", "occ"}


@dataclass(slots=True)
class Settings:
    platform_root: Path
    workspace_root: Path
    data_root: Path
    aieng_root: Path
    sample_step: Path

    @property
    def projects_root(self) -> Path:
        return self.data_root / "projects"

    @property
    def runtime_config_path(self) -> Path:
        return self.data_root / RUNTIME_CONFIG_FILENAME

    @classmethod
    def from_env(cls) -> "Settings":
        platform_root = PLATFORM_ROOT
        workspace_root = WORKSPACE_ROOT
        sample_override = os.environ.get("AIENG_SAMPLE_STEP")
        if sample_override:
            sample_step = Path(sample_override).resolve()
        else:
            candidates = (
                workspace_root / "SFA-5.41" / "nist_ctc_05.stp",
                workspace_root / "aieng" / "examples" / "bracket.step",
            )
            sample_step = next(
                (path.resolve() for path in candidates if path.exists()),
                candidates[0].resolve(),
            )
        return cls(
            platform_root=platform_root,
            workspace_root=workspace_root,
            data_root=Path(os.environ.get("AIENG_PLATFORM_DATA", platform_root / "data")).resolve(),
            aieng_root=Path(os.environ.get("AIENG_ROOT", workspace_root / "aieng")).resolve(),
            sample_step=sample_step,
        )


PROJECT_TEMPLATE = {
    "id": "",
    "name": "",
    "status": "empty",
    "created_at": "",
    "updated_at": "",
    "source_step": None,
    "aieng_file": None,
    "web_asset": None,
    "web_asset_format": None,
    "preview_info": None,
    "last_validation_ok": None,
    "last_error": None,
    "last_chat_audit": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
