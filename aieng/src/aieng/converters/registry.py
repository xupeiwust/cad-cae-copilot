"""Registry of available CAD/CAE-to-.aieng converters (Phase 20)."""
from __future__ import annotations

from typing import Callable

from .base import Converter


_REGISTRY: dict[str, Callable[[], Converter]] = {}


def register_converter(converter_id: str, factory: Callable[[], Converter]) -> None:
    """Register a converter factory under a stable id."""
    if not converter_id:
        raise ValueError("converter_id must not be empty")
    _REGISTRY[converter_id] = factory


def get_converter(converter_id: str) -> Converter:
    if converter_id not in _REGISTRY:
        raise KeyError(f"converter not registered: {converter_id}")
    return _REGISTRY[converter_id]()


def available_converters() -> list[str]:
    return sorted(_REGISTRY.keys())


def _bootstrap() -> None:
    """Register built-in reference converters lazily.

    Each built-in registration is best-effort: missing modules do not abort
    bootstrap. This keeps the framework usable when no reference converter
    has been installed alongside it.
    """
    try:
        from .freecad import FreeCADConverter
    except Exception:  # pragma: no cover - defensive
        FreeCADConverter = None  # type: ignore[assignment]

    if FreeCADConverter is not None and "freecad_reference" not in _REGISTRY:
        register_converter("freecad_reference", FreeCADConverter)


_bootstrap()
