"""Key/value settings routes (`/api/settings`).

Extracted from ``app_factory.create_app`` (#9), verbatim. These handlers depend
only on the SQLite ``db`` module and the ``db_path`` create_app local, so the
former is imported lazily (as in the original) and the latter is passed in.
"""

from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException


def register_settings_routes(app: FastAPI, *, db_path: Any) -> None:
    @app.get("/api/settings")
    def list_settings() -> dict[str, Any]:
        from .. import db

        all_settings = db.get_all_settings(db_path)
        all_settings.pop("api_key", None)
        return all_settings

    @app.get("/api/settings/{key}")
    def get_setting_endpoint(key: str) -> dict[str, Any]:
        from .. import db

        record = db.get_setting_record(db_path, key)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Setting not found: {key}")
        return record

    @app.put("/api/settings/{key}")
    def put_setting_endpoint(
        key: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        from .. import db

        p = payload or {}
        try:
            return db.set_setting(db_path, key, p.get("value"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/settings/{key}")
    def delete_setting_endpoint(key: str) -> dict[str, Any]:
        from .. import db

        try:
            deleted = db.delete_setting(db_path, key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Setting not found: {key}")
        return {"deleted": True, "key": key}
