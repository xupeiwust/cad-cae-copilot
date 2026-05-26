from __future__ import annotations

import json
from pathlib import Path

import pytest

from aieng.cli import main


class TestCliPlan:
    def test_plan_writes_file(self, tmp_path: Path, capsys) -> None:
        out_path = tmp_path / "plan.json"
        rc = main(
            [
                "plan",
                "--intent",
                "create a 120x80x10 plate with 4 holes",
                "--out",
                str(out_path),
            ]
        )
        assert rc == 0
        assert out_path.exists()

        with open(out_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        assert plan["plan_schema_version"] == "0.1.0"
        assert any(s["operation"] == "create_box" for s in plan["steps"])

    def plan_json_stdout(self, tmp_path: Path, capsys) -> None:
        out_path = tmp_path / "plan.json"
        rc = main(
            [
                "plan",
                "--intent",
                "create a 120x80x10 plate with 4 holes",
                "--out",
                str(out_path),
                "--json",
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        # Second JSON block in stdout
        stdout_plan = json.loads(captured.out.strip().split("\n")[-1])
        assert stdout_plan["plan_schema_version"] == "0.1.0"

    def test_plan_invalid_intent_still_generates(self, tmp_path: Path) -> None:
        """Even vague intent should generate a valid plan using defaults."""
        out_path = tmp_path / "plan.json"
        rc = main(
            [
                "plan",
                "--intent",
                "make something",
                "--out",
                str(out_path),
            ]
        )
        assert rc == 0
        with open(out_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        assert len(plan["steps"]) >= 1

    def test_plan_custom_units(self, tmp_path: Path) -> None:
        out_path = tmp_path / "plan.json"
        rc = main(
            [
                "plan",
                "--intent",
                "create a 12x8x1 plate",
                "--out",
                str(out_path),
                "--units",
                "cm",
            ]
        )
        assert rc == 0
        with open(out_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        assert plan["units"]["length"] == "cm"


class TestCliValidatePlan:
    def test_validate_plan_pass(self, tmp_path: Path, capsys) -> None:
        plan = {
            "plan_id": "p1",
            "plan_schema_version": "0.1.0",
            "intent": {"original_text": "test"},
            "units": {"length": "mm", "angle": "deg"},
            "steps": [
                {
                    "step_id": "step_001",
                    "operation": "create_box",
                    "creates": "b1",
                    "parameters": {
                        "length": 10.0,
                        "width": 10.0,
                        "height": 10.0,
                        "name": "b1",
                    },
                }
            ],
        }
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        rc = main(["validate-plan", str(plan_path)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_validate_plan_fail(self, tmp_path: Path, capsys) -> None:
        plan = {
            "plan_id": "p1",
            "plan_schema_version": "0.1.0",
            "intent": {"original_text": "test"},
            "units": {"length": "mm", "angle": "deg"},
            "steps": [
                {
                    "step_id": "step_001",
                    "operation": "create_plate",
                    "creates": "b1",
                    "parameters": {"length": 10.0},
                }
            ],
        }
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        rc = main(["validate-plan", str(plan_path)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.out

    def test_validate_plan_missing_file(self, capsys) -> None:
        rc = main(["validate-plan", "/nonexistent/plan.json"])
        assert rc == 2
        captured = capsys.readouterr()
        assert "FAIL" in captured.err
