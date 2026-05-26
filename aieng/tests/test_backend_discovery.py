from __future__ import annotations

import pytest

from aieng.backend_discovery import discover_backend
from aieng.backends.fake_backend import FakeBackend


class TestDiscoverBackend:
    def test_discover_fake_by_name(self) -> None:
        cls = discover_backend("fake")
        assert cls is FakeBackend

    def test_discover_by_dotted_path_colon(self) -> None:
        cls = discover_backend("aieng.backends.fake_backend:FakeBackend")
        assert cls is FakeBackend

    def test_discover_by_dotted_path_dot(self) -> None:
        cls = discover_backend("aieng.backends.fake_backend.FakeBackend")
        assert cls is FakeBackend

    def test_unknown_backend_raises_import_error(self) -> None:
        with pytest.raises(ImportError):
            discover_backend("nonexistent_backend_xyz")

    def test_invalid_class_raises_import_error(self) -> None:
        with pytest.raises(ImportError):
            discover_backend("aieng.backends.fake_backend:NonExistentClass")

    def test_invalid_module_raises_import_error(self) -> None:
        with pytest.raises(ImportError):
            discover_backend("aieng.nonexistent.module:FakeBackend")

    def test_does_not_import_freecad_mcp(self) -> None:
        """Ensure core discovery does not hard-import the FreeCAD adapter."""
        import sys
        freecad_mod = "aieng_freecad_mcp"
        # The module may or may not be importable in this environment,
        # but it must not appear in sys.modules as a side effect of discovery.
        before = set(sys.modules.keys())
        discover_backend("fake")
        after = set(sys.modules.keys())
        new_modules = after - before
        assert not any(freecad_mod in m for m in new_modules)
