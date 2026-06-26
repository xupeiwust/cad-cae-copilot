from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "run_real_ccx_verification_gate.py"
_SPEC = importlib.util.spec_from_file_location("real_ccx_gate", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gate
_SPEC.loader.exec_module(gate)


def test_split_ccx_command_defaults_to_ccx() -> None:
    assert gate.split_ccx_command(None) == ["ccx"]
    assert gate.split_ccx_command("") == ["ccx"]


def test_split_ccx_command_preserves_conda_launcher() -> None:
    assert gate.split_ccx_command("conda run -n calculix-env ccx") == [
        "conda",
        "run",
        "-n",
        "calculix-env",
        "ccx",
    ]


def test_build_pythonpath_contains_core_and_backend_paths() -> None:
    path = gate.build_pythonpath(_ROOT, "existing")
    parts = path.split(os.pathsep)
    assert str(_ROOT / "aieng" / "src") in parts
    assert str(_ROOT / "aieng") in parts
    assert str(_ROOT / "aieng-ui" / "backend") in parts
    assert "existing" in parts


def test_parse_junit_summary_counts_root_testsuite(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        '<testsuite tests="3" failures="1" errors="0" skipped="1"></testsuite>',
        encoding="utf-8",
    )
    summary = gate.parse_junit_summary(junit)
    assert summary.tests == 3
    assert summary.failures == 1
    assert summary.errors == 0
    assert summary.skipped == 1


def test_parse_junit_summary_counts_testsuites_children(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        """
        <testsuites>
          <testsuite tests="2" failures="0" errors="0" skipped="1"></testsuite>
          <testsuite tests="4" failures="1" errors="1" skipped="0"></testsuite>
        </testsuites>
        """,
        encoding="utf-8",
    )
    summary = gate.parse_junit_summary(junit)
    assert summary.tests == 6
    assert summary.failures == 1
    assert summary.errors == 1
    assert summary.skipped == 1


def test_selected_targets() -> None:
    assert [target.label for target in gate.selected_targets("all")] == [
        "NAFEMS real-ccx numerical verification",
        "Backend CAD->CAE real-ccx solve loop",
    ]
    assert gate.selected_targets("nafems") == [gate.TARGETS["nafems"]]


def test_main_requires_resolvable_ccx_unless_skips_are_allowed(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("AIENG_CCX_CMD", "/definitely/missing/ccx")
    monkeypatch.setattr(gate, "run_target", lambda *args, **kwargs: calls.append(args) or 0)
    assert gate.main(["--suite", "nafems"]) == 2
    assert calls == []
    assert gate.main(["--suite", "nafems", "--allow-skips"]) == 0
    assert len(calls) == 1
