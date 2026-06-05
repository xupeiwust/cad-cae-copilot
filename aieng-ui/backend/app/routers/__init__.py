"""HTTP route modules for the FastAPI backend.

Incremental decomposition of the historically monolithic ``app_factory.py``
(#9). Each module exposes a ``register_<group>_routes(app, ...)`` function that
``create_app`` calls to attach that group's endpoints. Routes are kept as
closures (matching the original structure) but live in focused files; shared
``create_app`` locals (settings, timestamps, worker registries) are passed in
explicitly instead of captured implicitly, and the helper functions each module
needs are imported from their real source modules rather than relying on
``app_factory``'s legacy ``_sync_main_symbols`` global copy.

Monkeypatch-sensitive helpers that live on ``app.main`` (e.g. ``runtime_status``)
are referenced through the ``app.main`` module at request time so test
monkeypatches keep working.
"""
