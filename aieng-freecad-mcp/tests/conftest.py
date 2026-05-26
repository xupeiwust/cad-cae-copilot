import pytest


def pytest_runtest_setup(item):
    """Skip @pytest.mark.freecad tests when FreeCAD is not importable."""
    if "freecad" in item.keywords:
        try:
            import FreeCAD  # noqa: F401
        except ImportError:
            pytest.skip("FreeCAD is not importable")
