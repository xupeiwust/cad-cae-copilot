"""Compatibility bridge for code historically nested in ``create_app``.

The extracted registrars still resolve the broad legacy symbol surface from
``app.main`` while the remaining business logic is moved to explicit modules.
Keeping that behavior in one place makes the progressive refactor auditable.
"""

from __future__ import annotations

from typing import Any


def sync_main_symbols(namespace: dict[str, Any]) -> None:
    from . import main as api

    namespace.update(
        {
            name: value
            for name, value in vars(api).items()
            if not (name.startswith("__") and name.endswith("__"))
        }
    )
