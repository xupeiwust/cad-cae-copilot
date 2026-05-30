from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import AutopilotRunState


class AutopilotStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        clean = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        return self.runs_dir / f"{clean}.json"

    def _cancel_path(self, run_id: str) -> Path:
        clean = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        return self.runs_dir / f"{clean}.cancel"

    def save(self, state: AutopilotRunState) -> None:
        path = self._path(state.run_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)

    def load(self, run_id: str) -> AutopilotRunState:
        path = self._path(run_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyError(f"Autopilot run not found: {run_id}") from None
        except Exception as exc:
            raise ValueError(f"Autopilot run file is unreadable: {exc}") from exc
        try:
            return AutopilotRunState.model_validate(data)
        except Exception as exc:
            raise ValueError(f"Autopilot run file is invalid: {exc}") from exc

    def request_cancel(self, run_id: str) -> None:
        self._cancel_path(run_id).write_text("cancelled", encoding="utf-8")

    def clear_cancel(self, run_id: str) -> None:
        try:
            self._cancel_path(run_id).unlink()
        except FileNotFoundError:
            pass

    def is_cancel_requested(self, run_id: str) -> bool:
        return self._cancel_path(run_id).exists()
