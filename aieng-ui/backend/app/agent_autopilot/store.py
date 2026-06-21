from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

from filelock import FileLock, Timeout

from .schema import AgentPlan, AutopilotRunState

LOGGER = logging.getLogger(__name__)

# Per-run read lock timeout for list_runs. Long enough to wait out a concurrent
# save() (which holds the lock only for an atomic write), so an in-flight run is
# not silently dropped from the listing — cleanup paths rely on completeness.
_LIST_RUNS_LOCK_TIMEOUT = 5.0


class AutopilotStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache for list_runs keyed by (project_id, session_id).
        # Invalidated on every mutating operation (save, delete_run, delete_runs).
        self._list_runs_cache: dict[tuple[str | None, str | None], list[AutopilotRunState]] = {}

    def _path(self, run_id: str) -> Path:
        clean = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        return self.runs_dir / f"{clean}.json"

    def _cancel_path(self, run_id: str) -> Path:
        clean = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        return self.runs_dir / f"{clean}.cancel"

    def _lock_path(self, run_id: str) -> Path:
        return self._path(run_id).with_suffix(".json.lock")

    def save(self, state: AutopilotRunState) -> None:
        path = self._path(state.run_id)
        lock_path = self._lock_path(state.run_id)
        tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")

        with FileLock(lock_path):
            tmp_path.write_text(
                state.model_dump_json(indent=2),
                encoding="utf-8",
            )
            last_error: PermissionError | None = None
            for attempt in range(8):
                try:
                    os.replace(tmp_path, path)
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.025 * (attempt + 1))
            else:
                try:
                    tmp_path.unlink()
                except FileNotFoundError:
                    pass
                if last_error is not None:
                    raise last_error

        # Invalidate cache on write so subsequent list_runs() reflects the change.
        self._list_runs_cache.clear()

    def load(self, run_id: str) -> AutopilotRunState:
        path = self._path(run_id)
        lock_path = self._lock_path(run_id)

        with FileLock(lock_path):
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

    def load_plan(self, run_id: str) -> AgentPlan | None:
        return self.load(run_id).plan

    def list_runs(self, *, project_id: str | None = None, session_id: str | None = None) -> list[AutopilotRunState]:
        cache_key = (project_id, session_id)
        if cache_key in self._list_runs_cache:
            # Return a copy so callers mutating the result (e.g. cancellation
            # paths that flip state.status) don't corrupt the cached list.
            return list(self._list_runs_cache[cache_key])

        all_runs = self._list_runs_cache.get((None, None))
        if all_runs is not None:
            runs = [
                state
                for state in all_runs
                if (project_id is None or state.project_id == project_id)
                and (session_id is None or state.session_id == session_id)
            ]
            self._list_runs_cache[cache_key] = runs
            return list(runs)

        runs: list[AutopilotRunState] = []
        for path in sorted(self.runs_dir.glob("*.json")):
            if path.suffix != ".json":
                continue
            lock_path = path.with_suffix(".json.lock")
            try:
                # Block briefly so a run mid-save() is included, not silently
                # dropped — cleanup/cancellation depends on a complete listing.
                with FileLock(lock_path, timeout=_LIST_RUNS_LOCK_TIMEOUT):
                    data = json.loads(path.read_text(encoding="utf-8"))
            except Timeout:
                # Could not acquire within the timeout — do NOT silently omit the
                # run; surface it so a missed cancellation is debuggable.
                LOGGER.warning("list_runs: timed out locking %s; omitting from listing", path.name)
                continue
            except Exception:
                LOGGER.warning("list_runs: failed to read %s; skipping", path.name, exc_info=True)
                continue
            try:
                state = AutopilotRunState.model_validate(data)
            except Exception:
                LOGGER.warning("list_runs: invalid run state in %s; skipping", path.name)
                continue
            runs.append(state)

        self._list_runs_cache[(None, None)] = runs
        if cache_key == (None, None):
            return list(runs)

        filtered_runs = [
            state
            for state in runs
            if (project_id is None or state.project_id == project_id)
            and (session_id is None or state.session_id == session_id)
        ]
        self._list_runs_cache[cache_key] = filtered_runs
        return list(filtered_runs)

    def delete_run(self, run_id: str) -> bool:
        deleted = False
        for path in (self._path(run_id), self._cancel_path(run_id)):
            try:
                path.unlink()
                deleted = True
            except FileNotFoundError:
                pass
        self._list_runs_cache.clear()
        return deleted

    def delete_runs(self, *, project_id: str | None = None, session_id: str | None = None) -> int:
        if project_id is None and session_id is None:
            raise ValueError("project_id or session_id is required")
        removed = 0
        for state in self.list_runs(project_id=project_id, session_id=session_id):
            if self.delete_run(state.run_id):
                removed += 1
        return removed

    def request_cancel(self, run_id: str) -> None:
        self._cancel_path(run_id).write_text("cancelled", encoding="utf-8")

    def clear_cancel(self, run_id: str) -> None:
        try:
            self._cancel_path(run_id).unlink()
        except FileNotFoundError:
            pass

    def is_cancel_requested(self, run_id: str) -> bool:
        return self._cancel_path(run_id).exists()
