from __future__ import annotations

import re
from pathlib import Path


def test_source_avoids_datetime_utc_import_for_runtime_compatibility():
    root = Path(__file__).resolve().parents[1]
    checked_files = [
        root / "src" / "aieng" / "package.py",
        root / "src" / "aieng" / "simulation" / "deck_exporter.py",
        root / "src" / "aieng" / "validation" / "status_writer.py",
    ]

    for path in checked_files:
        text = path.read_text(encoding="utf-8")
        assert "from datetime import UTC" not in text, f"{path} should avoid datetime.UTC import"


def test_source_avoids_pep_604_type_unions_inside_isinstance_calls():
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"isinstance\([^\n]*\|")

    for path in (root / "src" / "aieng").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert pattern.search(text) is None, f"{path} should avoid PEP 604 unions inside isinstance()"
