"""Project artifact, conversion, chat-session, and chat-message routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from ..legacy_app_symbols import sync_main_symbols
from ..logging_utils import log_exception

LOGGER = logging.getLogger("app.app_factory")


def _sync_main_symbols() -> None:
    sync_main_symbols(globals())


from .agent import _agent_plan_response_from_run


def register_project_chat_routes(
    app: FastAPI,
    *,
    active_settings: Any,
    db_path: Any,
    app_context: Any,
) -> None:
    _sync_main_symbols()
    _add_chat_message_and_publish = app_context.add_chat_message_and_publish
    _autopilot_store = app_context.autopilot_store
    _cancel_session_autopilot_runs = app_context.cancel_session_autopilot_runs
    _publish_chat_session_event = app_context.publish_chat_session_event
    _publish_live_event = app_context.publish_live_event

    @app.get("/api/projects/{project_id}/artifact")
    def get_project_artifact(project_id: str, path: str = "") -> dict[str, Any]:
        """Read a single artifact from the project's .aieng package.

        Phase 26 — evidence review groundwork. Read-only. Does NOT execute
        solvers, mutate packages, or advance claims.

        Query parameters:
            path: Artifact path inside the package, e.g.
                  ``results/computed_metrics.json``. Must be a relative path
                  with forward slashes; leading ``/``, backslashes, ``.``,
                  and ``..`` segments are rejected with 400.

        Returns:
            ``{path, exists, media_type, size_bytes?, parsed_json?, text?, warnings}``.
            ``exists=false`` returns 200, not 404, so callers can probe
            artifact presence without exception handling. The package
            itself missing returns 404.
        """
        if not _is_safe_artifact_path(path):
            raise HTTPException(
                status_code=400,
                detail=(
                    "invalid artifact path: must be a relative archive path "
                    "with no leading '/', no '..' segments, and no backslashes"
                ),
            )
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        return _read_artifact_from_package(package_path, path)

    @app.post("/api/projects/{project_id}/solver-input")
    def import_solver_input(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Import a CalculiX `.inp` solver input deck into the package.

        Phase 29 — closes the biggest functional gap in the vertical CAE MVP
        (the runtime previously required a pre-existing deck inside the
        package). This endpoint writes a caller-supplied deck to the
        canonical run path so ``cae.run_solver`` and ``cae.prepare_solver_run``
        can find it.

        Import only. Does NOT execute the solver, generate a mesh, generate a
        deck, or validate physical correctness. The minimal parse below just
        scans for CalculiX keyword lines so obviously empty or wrong-format
        bodies are rejected with a 400.

        Body:
            ``text`` (str, required): the `.inp` content as utf-8 text.
            ``run_id`` (str, optional): defaults to ``"run_001"``.
                Must match ``^[a-zA-Z0-9_-]{1,64}$``.
            ``overwrite`` (bool, optional): defaults to ``True``.

        Returns:
            ``{ok, package_path, artifact, keyword_count, keywords, warnings}``.
            The deck lands at ``simulation/runs/{run_id}/solver_input.inp``.
        """
        body = payload or {}
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(
                status_code=400,
                detail="body must contain a non-empty 'text' string with the .inp content",
            )
        size_bytes = len(text.encode("utf-8"))
        if size_bytes > _SOLVER_INPUT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"solver input deck {size_bytes} bytes exceeds cap "
                    f"{_SOLVER_INPUT_MAX_BYTES}"
                ),
            )
        run_id = str(body.get("run_id") or "run_001")
        if not _is_safe_run_id(run_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    "run_id must match ^[a-zA-Z0-9_-]{1,64}$ "
                    "(no path separators, no traversal)"
                ),
            )
        overwrite = bool(body.get("overwrite", True))

        parse = _parse_calculix_input_deck(text)
        if parse["keyword_count"] == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "no CalculiX keywords found in body 'text'; "
                    "expected at least one line starting with '*'"
                ),
            )

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        artifact_path = f"simulation/runs/{run_id}/solver_input.inp"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".inp", delete=False, encoding="utf-8", newline=""
        ) as fh:
            fh.write(text)
            tmp_path = Path(fh.name)
        try:
            try:
                artifact = write_artifact_to_package(
                    package_path,
                    artifact_path,
                    tmp_path,
                    overwrite=overwrite,
                )
            except FileExistsError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        artifact["kind"] = "solver_input"
        artifact["role"] = "solver_input_deck"
        artifact["size_bytes"] = size_bytes
        artifact.pop("source_path", None)

        return {
            "ok": True,
            "package_path": str(package_path),
            "run_id": run_id,
            "artifact": artifact,
            "keyword_count": parse["keyword_count"],
            "keywords": parse["keywords"],
            "warnings": parse["warnings"],
        }

    @app.post("/api/projects/{project_id}/artifact/diff")
    def diff_project_artifact(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Compute changed JSON pointer paths between two arbitrary JSON values.

        Phase 26 — paired with the artifact read endpoint so callers can
        capture before/after JSON snapshots themselves and ask the server
        for a structural diff. Pure computation; no package access.

        Body:
            ``{"before": <any>, "after": <any>}``

        Returns:
            ``{"changed_paths": [...], "added_paths": [...], "removed_paths": [...]}``.
            Paths are RFC-6901 JSON pointers.
        """
        get_project(active_settings, project_id)
        body = payload or {}
        if "before" not in body or "after" not in body:
            raise HTTPException(
                status_code=400,
                detail="body must contain both 'before' and 'after' keys",
            )
        changed, added, removed = _json_diff_paths(body["before"], body["after"])
        return {
            "changed_paths": changed,
            "added_paths": added,
            "removed_paths": removed,
        }

    @app.post("/api/projects/{project_id}/import-aieng")
    def import_project(project_id: str) -> dict[str, Any]:
        result = import_aieng_file(active_settings, project_id)
        audit_meta = write_audit_log(active_settings, project_id, "import", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/validate")
    def validate_project(project_id: str) -> dict[str, Any]:
        result = validate_aieng_file(active_settings, project_id)
        audit_meta = write_audit_log(active_settings, project_id, "validate", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/convert")
    def convert_project(project_id: str) -> dict[str, Any]:
        result = convert_asset(active_settings, project_id)
        audit_meta = write_audit_log(active_settings, project_id, "convert", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/mcp/check")
    def mcp_check_endpoint(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        result = mcp_check(active_settings, project_id, payload or {})
        audit_meta = write_audit_log(active_settings, project_id, "mcp_check", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/mcp/parse-patch")
    def parse_patch_endpoint(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        get_project(active_settings, project_id)
        result = parse_patch(active_settings, payload or {})
        audit_meta = write_audit_log(active_settings, project_id, "parse_patch", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/mcp/prepare-execution")
    def prepare_execution_endpoint(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        result = prepare_patch_execution(active_settings, project_id, payload or {})
        audit_meta = write_audit_log(active_settings, project_id, "prepare_execution", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/chat")
    def chat(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        from .. import db

        p = payload or {}
        message = str(p.get("message") or "").strip()
        session_id = str(p.get("session_id") or "").strip() or None
        if session_id is None:
            session_id = db.ensure_default_chat_session(db_path, project_id)["id"]
        if message:
            _add_chat_message_and_publish(
                project_id=project_id,
                session_id=session_id,
                role="user",
                content=message,
            )
        result = chat_orchestrator(active_settings, project_id, p)
        reply = result.get("reply", "")
        if reply:
            _add_chat_message_and_publish(
                project_id=project_id,
                session_id=session_id,
                role="assistant",
                content=reply,
            )
        return result

    @app.get("/api/projects/{project_id}/chat-sessions")
    def list_chat_sessions(project_id: str) -> list[dict[str, Any]]:
        from .. import db

        get_project(active_settings, project_id)
        sessions = db.get_chat_sessions(db_path, project_id)
        if not sessions:
            sessions = [db.ensure_default_chat_session(db_path, project_id)]
        return sessions

    @app.post("/api/projects/{project_id}/chat-sessions")
    def create_chat_session_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        from .. import db

        get_project(active_settings, project_id)
        p = payload or {}
        try:
            session = db.create_chat_session(
                db_path,
                project_id=project_id,
                title=str(p.get("title") or "New session"),
            )
            _publish_chat_session_event(session, "created")
            return session
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/projects/{project_id}/chat-sessions/{session_id}")
    def update_chat_session_endpoint(
        project_id: str,
        session_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        from .. import db

        get_project(active_settings, project_id)
        p = payload or {}
        try:
            updated = db.update_chat_session(
                db_path,
                session_id,
                title=p.get("title") if isinstance(p.get("title"), str) else None,
                status=p.get("status") if isinstance(p.get("status"), str) else None,
                active_run_id=p.get("active_run_id") if isinstance(p.get("active_run_id"), str) else None,
                approval_mode=p.get("approval_mode") if isinstance(p.get("approval_mode"), str) else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if updated is None or updated["project_id"] != project_id:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        _publish_chat_session_event(updated)
        return updated

    @app.get("/api/projects/{project_id}/chat-sessions/{session_id}/agent-plan")
    def get_chat_session_agent_plan(project_id: str, session_id: str) -> dict[str, Any]:
        from .. import db

        get_project(active_settings, project_id)
        session = db.get_chat_session(db_path, session_id)
        if session is None or session["project_id"] != project_id:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        run_id = session.get("active_run_id")
        if not run_id:
            return {
                "run_id": None,
                "project_id": project_id,
                "session_id": session_id,
                "plan": None,
                "run_status": session.get("status"),
                "updated_at": session.get("updated_at"),
            }
        store = _autopilot_store()
        try:
            return _agent_plan_response_from_run(store.load(str(run_id)))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def _require_chat_session(project_id: str, session_id: str) -> dict[str, Any]:
        from .. import db

        get_project(active_settings, project_id)
        session = db.get_chat_session(db_path, session_id)
        if session is None or session["project_id"] != project_id:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        return session

    def _context_summary_response(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": session["project_id"],
            "session_id": session["id"],
            "context_summary": session.get("context_summary"),
            "context_summary_updated_at": session.get("context_summary_updated_at"),
        }

    def _redact_context_summary_text(value: Any, *, limit: int = 360) -> str:
        from ..agent_autopilot.context_summary import redact_context_summary_text

        return redact_context_summary_text(value, limit=limit)

    def _build_rule_context_summary(project_id: str, session: dict[str, Any]) -> dict[str, Any]:
        from .. import db
        from ..agent_autopilot.context_summary import build_context_summary

        messages = db.get_chat_messages(db_path, project_id, session_id=session["id"])
        events = db.get_agent_events(db_path, project_id, session_id=session["id"])
        run = None
        run_id = session.get("active_run_id")
        if run_id:
            try:
                run = _autopilot_store().load(str(run_id))
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to load autopilot run while building context summary.",
                    subsystem="app_factory.context_summary.load_run",
                    context={"project_id": project_id, "run_id": run_id},
                )
                run = None
        return build_context_summary(
            project_id=project_id,
            session=session,
            messages=messages,
            events=events,
            run=run,
        ).model_dump()

    @app.get("/api/projects/{project_id}/chat-sessions/{session_id}/context-summary")
    def get_chat_session_context_summary(project_id: str, session_id: str) -> dict[str, Any]:
        return _context_summary_response(_require_chat_session(project_id, session_id))

    @app.put("/api/projects/{project_id}/chat-sessions/{session_id}/context-summary")
    def update_chat_session_context_summary_endpoint(
        project_id: str,
        session_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        from pydantic import ValidationError
        from .. import db
        from ..agent_autopilot.schema import ContextSummary

        _require_chat_session(project_id, session_id)
        data = payload or {}
        raw_summary = data.get("context_summary") if "context_summary" in data else data
        if raw_summary is None:
            updated = db.update_chat_session_context_summary(db_path, session_id, context_summary=None)
            if updated is None:
                raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
            _publish_chat_session_event(updated)
            return _context_summary_response(updated)
        if not isinstance(raw_summary, dict):
            raise HTTPException(status_code=400, detail="context_summary must be an object or null")
        try:
            summary = ContextSummary.model_validate(raw_summary)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors()) from exc
        if summary.project_id != project_id or summary.session_id != session_id:
            raise HTTPException(status_code=400, detail="context_summary session_id/project_id must match the URL")
        updated = db.update_chat_session_context_summary(
            db_path,
            session_id,
            context_summary=summary.model_dump(),
            updated_at=summary.updated_at,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        _publish_chat_session_event(updated)
        return _context_summary_response(updated)

    @app.post("/api/projects/{project_id}/chat-sessions/{session_id}/context-summary/refresh")
    def refresh_chat_session_context_summary(project_id: str, session_id: str) -> dict[str, Any]:
        from .. import db

        session = _require_chat_session(project_id, session_id)
        summary = _build_rule_context_summary(project_id, session)
        updated = db.update_chat_session_context_summary(
            db_path,
            session_id,
            context_summary=summary,
            updated_at=str(summary.get("updated_at") or ""),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        _publish_chat_session_event(updated)
        return _context_summary_response(updated)

    @app.delete("/api/projects/{project_id}/chat-sessions/{session_id}")
    def delete_chat_session_endpoint(project_id: str, session_id: str) -> dict[str, Any]:
        from .. import db

        get_project(active_settings, project_id)
        session = db.get_chat_session(db_path, session_id)
        if session is None or session.get("project_id") != project_id:
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        cancelled_runs = _cancel_session_autopilot_runs(project_id, session_id)
        if not db.delete_chat_session(db_path, project_id, session_id):
            raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        # Session row is gone — now remove this session's autopilot run files from
        # disk so they don't linger as orphans (B-12). delete_runs sweeps by
        # session_id only; runs belonging to other sessions are untouched. Done
        # after the DB delete succeeds so a failed delete never strands run files;
        # a store failure here surfaces as a 500 rather than silent inconsistency.
        deleted_run_files = _autopilot_store().delete_runs(session_id=session_id)
        _publish_live_event({
            "type": "chat_session_deleted",
            "project_id": project_id,
            "session_id": session_id,
            "cancelled_autopilot_runs": cancelled_runs,
            "deleted_autopilot_run_files": deleted_run_files,
        })
        return {
            "deleted": True,
            "project_id": project_id,
            "session_id": session_id,
            "cancelled_autopilot_runs": cancelled_runs,
            "deleted_autopilot_run_files": deleted_run_files,
        }

    @app.get("/api/projects/{project_id}/chat-messages")
    def list_chat_messages(project_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        from .. import db

        get_project(active_settings, project_id)
        if session_id:
            session = db.get_chat_session(db_path, session_id)
            if session is None or session["project_id"] != project_id:
                raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        return db.get_chat_messages(db_path, project_id, session_id=session_id)

    @app.get("/api/projects/{project_id}/agent-events")
    def list_agent_events(project_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        from .. import db

        get_project(active_settings, project_id)
        if session_id:
            session = db.get_chat_session(db_path, session_id)
            if session is None or session["project_id"] != project_id:
                raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        return db.get_agent_events(db_path, project_id, session_id=session_id)

    @app.post("/api/projects/{project_id}/chat-messages")
    def create_chat_message(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        from .. import db

        p = payload or {}
        get_project(active_settings, project_id)
        session_id = str(p.get("session_id") or "").strip() or None
        try:
            return _add_chat_message_and_publish(
                project_id=project_id,
                session_id=session_id,
                role=str(p.get("role", "user")),
                content=str(p.get("content") or ""),
                mode=p.get("mode") if p.get("mode") else None,
                created_at=p.get("created_at") if p.get("created_at") else None,
                extra=p.get("extra") if isinstance(p.get("extra"), dict) else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/projects/{project_id}/chat-messages")
    def delete_chat_messages(project_id: str, session_id: str | None = None) -> dict[str, Any]:
        from .. import db

        get_project(active_settings, project_id)
        if session_id:
            session = db.get_chat_session(db_path, session_id)
            if session is None or session["project_id"] != project_id:
                raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
        deleted = db.clear_chat_messages(db_path, project_id, session_id=session_id)
        return {"deleted": deleted, "project_id": project_id}
