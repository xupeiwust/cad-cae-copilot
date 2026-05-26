"""Tests for computed_metrics_exporter.

No FreeCAD dependency required.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from freecad_mcp.computed_metrics_exporter import (
    ComputedMetricsExportError,
    export_computed_metrics,
    main,
)


class TestExportComputedMetrics:
    def test_flat_json_input(self, tmp_path: Path) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps({
                "max_von_mises_stress_mpa": 187.4,
                "max_displacement_mm": 0.82,
                "factor_of_safety": 1.33,
            }),
            encoding="utf-8",
        )
        output_file = tmp_path / "computed_metrics.json"

        result = export_computed_metrics(
            input_file,
            output_file,
            load_case_id="lc_001",
            software="FreeCAD FEM / CalculiX",
        )

        assert result["schema_version"] == "0.1"
        assert result["metrics_source"]["software"] == "FreeCAD FEM / CalculiX"
        assert result["metrics_source"]["tool"] == "freecad_mcp_postprocessor"
        assert len(result["load_cases"]) == 1
        assert result["load_cases"][0]["id"] == "lc_001"

        metrics = result["load_cases"][0]["metrics"]
        assert metrics["max_von_mises_stress"]["value"] == 187.4
        assert metrics["max_von_mises_stress"]["unit"] == "MPa"
        assert metrics["max_displacement"]["value"] == 0.82
        assert metrics["max_displacement"]["unit"] == "mm"
        assert metrics["minimum_safety_factor"]["value"] == 1.33
        assert metrics["minimum_safety_factor"]["unit"] is None

        # File was written
        assert output_file.exists()
        parsed = json.loads(output_file.read_text(encoding="utf-8"))
        assert parsed["load_cases"][0]["metrics"]["max_von_mises_stress"]["value"] == 187.4

    def test_csv_input(self, tmp_path: Path) -> None:
        input_file = tmp_path / "input.csv"
        input_file.write_text(
            "name,value,unit\n"
            "max_von_mises_stress_mpa,200.5,MPa\n"
            "max_displacement_mm,1.23,mm\n",
            encoding="utf-8",
        )
        output_file = tmp_path / "computed_metrics.json"

        result = export_computed_metrics(input_file, output_file, load_case_id="lc_csv")

        metrics = result["load_cases"][0]["metrics"]
        assert metrics["max_von_mises_stress"]["value"] == 200.5
        assert metrics["max_displacement"]["value"] == 1.23

    def test_phase6_schema_input_validated(self, tmp_path: Path) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps({
                "schema_version": "0.1",
                "metrics_source": {
                    "tool": "custom_postprocessor",
                    "software": "Ansys Mechanical",
                    "source_files": ["results.rst"],
                },
                "load_cases": [
                    {
                        "id": "lc1",
                        "metrics": {
                            "max_von_mises_stress": {
                                "value": 150.0,
                                "unit": "MPa",
                                "location": {"type": "element", "id": 42},
                            },
                        },
                    }
                ],
            }),
            encoding="utf-8",
        )
        output_file = tmp_path / "computed_metrics.json"

        result = export_computed_metrics(input_file, output_file)

        assert result["metrics_source"]["tool"] == "custom_postprocessor"
        assert result["load_cases"][0]["metrics"]["max_von_mises_stress"]["value"] == 150.0
        assert result["load_cases"][0]["metrics"]["max_von_mises_stress"]["location"]["type"] == "element"

    def test_missing_input_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            export_computed_metrics(tmp_path / "missing.json", tmp_path / "out.json")

    def test_malformed_input_raises(self, tmp_path: Path) -> None:
        input_file = tmp_path / "bad.json"
        input_file.write_text("not json", encoding="utf-8")
        with pytest.raises(ComputedMetricsExportError):
            export_computed_metrics(input_file, tmp_path / "out.json")

    def test_empty_input_warns(self, tmp_path: Path) -> None:
        input_file = tmp_path / "empty.json"
        input_file.write_text("{}", encoding="utf-8")
        output_file = tmp_path / "out.json"
        result = export_computed_metrics(input_file, output_file)
        assert any("No recognized metrics" in w for w in result["warnings"])
        assert result["load_cases"][0]["metrics"] == {}

    def test_unrecognized_key_warns(self, tmp_path: Path) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps({"unknown_metric": 123, "max_von_mises_stress_mpa": 100.0}),
            encoding="utf-8",
        )
        output_file = tmp_path / "out.json"
        result = export_computed_metrics(input_file, output_file)
        assert any("Unrecognized" in w for w in result["warnings"])
        assert "max_von_mises_stress" in result["load_cases"][0]["metrics"]

    def test_metric_object_with_location_preserved(self, tmp_path: Path) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text(
            json.dumps({
                "max_von_mises_stress": {
                    "value": 180.0,
                    "unit": "MPa",
                    "location": {"type": "node", "id": 99, "coordinates": [1.0, 2.0, 3.0]},
                    "field": "von_mises_stress",
                },
            }),
            encoding="utf-8",
        )
        output_file = tmp_path / "out.json"
        result = export_computed_metrics(input_file, output_file)
        m = result["load_cases"][0]["metrics"]["max_von_mises_stress"]
        assert m["location"]["type"] == "node"
        assert m["location"]["coordinates"] == [1.0, 2.0, 3.0]
        assert m["field"] == "von_mises_stress"


class TestCli:
    def test_cli_success(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        input_file = tmp_path / "in.json"
        input_file.write_text(json.dumps({"max_von_mises_stress_mpa": 100.0}), encoding="utf-8")
        output_file = tmp_path / "out.json"

        rc = main(["--input", str(input_file), "--output", str(output_file), "--software", "TestSolver"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "ok" in captured.out
        # stdout is JSON; output path is escaped inside it
        parsed = json.loads(captured.out)
        assert parsed["output"] == str(output_file)

    def test_cli_missing_input(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["--input", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")])
        assert rc == 2
        captured = capsys.readouterr()
        assert "error" in captured.err

    def test_cli_stdout_is_json_only(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        input_file = tmp_path / "in.json"
        input_file.write_text(json.dumps({"factor_of_safety": 2.0}), encoding="utf-8")
        output_file = tmp_path / "out.json"

        rc = main(["--input", str(input_file), "--output", str(output_file)])
        assert rc == 0
        captured = capsys.readouterr()
        # stdout should be parseable JSON
        parsed = json.loads(captured.out)
        assert parsed["status"] == "ok"
        assert parsed["metrics_count"] == 1


class TestAiengRoundTrip:
    def test_exporter_output_ingested_by_aieng(self, tmp_path: Path) -> None:
        """Verify the exporter produces output that aieng can ingest."""
        # Only run if aieng is importable
        pytest.importorskip("aieng.cae_result_summary")

        input_file = tmp_path / "postprocess.json"
        input_file.write_text(
            json.dumps({
                "max_von_mises_stress_mpa": 210.5,
                "max_displacement_mm": 0.95,
                "factor_of_safety": 1.15,
            }),
            encoding="utf-8",
        )
        computed_metrics_path = tmp_path / "computed_metrics.json"
        export_computed_metrics(
            input_file,
            computed_metrics_path,
            load_case_id="lc_rt",
            software="RoundTripSolver",
        )

        # Build a minimal .aieng package containing the computed_metrics
        pkg = tmp_path / "roundtrip.aieng"
        with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps({"model_id": "rt", "resources": {}}))
            zf.writestr("results/computed_metrics.json", computed_metrics_path.read_bytes())

        from aieng.cae_result_summary import generate_cae_result_summary

        summary = generate_cae_result_summary(pkg)
        assert summary["schema_version"] == "0.3"
        assert summary["computed_values"]["extrema_computed"] is True
        assert summary["computed_values"]["computed_by"] == "freecad_mcp_postprocessor"
        assert summary["computed_values"]["max_von_mises_stress"]["value"] == 210.5
        assert summary["computed_values"]["max_displacement"]["value"] == 0.95
        assert summary["computed_values"]["minimum_safety_factor"]["value"] == 1.15

        # Verify load case merge
        lc = next((lc for lc in summary["load_cases"] if lc["id"] == "lc_rt"), None)
        assert lc is not None
        assert lc["metrics"]["max_von_mises_stress"]["value"] == 210.5
