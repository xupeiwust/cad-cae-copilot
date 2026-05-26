from __future__ import annotations

import importlib
import sys
from typing import Any


_BUILT_IN_BACKENDS: dict[str, str] = {
    "fake": "aieng.backends.fake_backend:FakeBackend",
}


def discover_backend(backend_id: str) -> type:
    """Discover a BackendAdapter class without hard cross-package imports.

    Resolution order:
      1. Built-in registry (e.g. ``"fake"``).
      2. ``importlib.metadata`` entry_points(group="aieng.backends").
      3. Dotted path fallback:
         ``"module.submodule:ClassName"`` or ``"module.submodule.ClassName"``.

    Raises:
        ImportError: if ``backend_id`` cannot be resolved to a class.
    """
    # 1. Built-in registry
    if backend_id in _BUILT_IN_BACKENDS:
        backend_id = _BUILT_IN_BACKENDS[backend_id]
        # Fall through to dotted-path resolution below

    # 2. Entry points
    entry_point_errors: list[str] = []
    try:
        if sys.version_info >= (3, 10):
            from importlib.metadata import entry_points
            eps = entry_points(group="aieng.backends")
        else:
            from importlib.metadata import entry_points
            all_eps = entry_points()
            eps = all_eps.get("aieng.backends", [])

        for ep in eps:
            if ep.name == backend_id:
                try:
                    return ep.load()
                except Exception as exc:
                    entry_point_errors.append(
                        f"Entry point '{ep.name}' from {ep.value} failed to load: {exc}"
                    )
                    break
    except Exception as exc:
        entry_point_errors.append(f"Entry point lookup failed: {exc}")

    # 3. Dotted path fallback
    module_path: str
    class_name: str

    if ":" in backend_id:
        module_path, _, class_name = backend_id.rpartition(":")
    elif "." in backend_id:
        module_path, _, class_name = backend_id.rpartition(".")
    else:
        module_path = ""
        class_name = backend_id

    if not module_path or not class_name:
        reasons = "; ".join(entry_point_errors) if entry_point_errors else "no entry point matched"
        raise ImportError(
            f"Backend '{backend_id}' is not a valid entry point or dotted path. ({reasons})"
        )

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        reasons = "; ".join(entry_point_errors) if entry_point_errors else "no entry point matched"
        raise ImportError(
            f"Could not import module '{module_path}' for backend '{backend_id}'. ({reasons})"
        ) from exc

    try:
        cls: type = getattr(module, class_name)
    except AttributeError as exc:
        reasons = "; ".join(entry_point_errors) if entry_point_errors else "no entry point matched"
        raise ImportError(
            f"Backend class '{class_name}' not found in {module_path}. ({reasons})"
        ) from exc

    return cls
