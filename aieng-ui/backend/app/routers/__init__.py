"""HTTP route modules for the FastAPI backend.

Incremental decomposition of the historically monolithic ``app_factory.py``
(#9). Each module exposes a ``register_<group>_routes(app, ...)`` function that
``create_app`` calls to attach that group's endpoints. Routes are kept as
closures (matching the original structure) but live in focused files; shared
``create_app`` locals are passed explicitly through the app context.

Monkeypatch-sensitive helpers that live on ``app.main`` (e.g. ``runtime_status``)
remain compatible through the centralized ``legacy_app_symbols`` bridge while
the progressive extraction moves dependencies to their owning modules.
"""
