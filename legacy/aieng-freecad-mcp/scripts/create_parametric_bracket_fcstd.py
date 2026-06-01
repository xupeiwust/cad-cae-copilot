"""Generate a parametric bracket FreeCAD fixture for the .aieng patch demo.

Usage:
    python scripts/create_parametric_bracket_fcstd.py

If FreeCAD is not available, the script exits cleanly with a skip message.

Generated artifacts:
    examples/parametric_bracket/freecad/source.FCStd
    examples/parametric_bracket/freecad/source.step
"""

from __future__ import annotations

import sys
from pathlib import Path


def _freecad_available() -> bool:
    try:
        import FreeCAD
        import Part
        return True
    except ImportError:
        return False


def create_bracket(output_dir: Path) -> dict:
    """Create a parametric bracket and save FCStd + STEP.

    Returns metadata about the created model.
    """
    import FreeCAD as App
    import Part

    doc = App.newDocument("ParametricBracket")

    # Base plate: Box with Length, Width, Thickness
    # Using a simple Part::Box for parametric editability
    base_plate = doc.addObject("Part::Box", "BasePlate")
    base_plate.Length = 100.0  # mm
    base_plate.Width = 60.0    # mm
    base_plate.Height = 10.0   # mm -> this is Thickness in the feature graph

    # Recompute to ensure validity
    doc.recompute()

    # Save FCStd
    fcstd_path = output_dir / "source.FCStd"
    doc.saveAs(str(fcstd_path))

    # Export STEP
    step_path = output_dir / "source.step"
    # Export the base plate shape
    base_plate.Shape.exportStep(str(step_path))

    return {
        "fcstd_path": str(fcstd_path),
        "step_path": str(step_path),
        "document": doc.Name,
        "objects": {
            "BasePlate": {
                "Length": base_plate.Length,
                "Width": base_plate.Width,
                "Height": base_plate.Height,
                "Volume_mm3": float(base_plate.Shape.Volume),
            }
        },
    }


def main() -> int:
    print("=" * 60)
    print(" Parametric Bracket Fixture Generator")
    print("=" * 60)

    if not _freecad_available():
        print("\nFreeCAD is not available. Skipping fixture generation.")
        print("To generate the fixture, run this script in an environment")
        print("where FreeCAD's Python modules are importable.")
        return 0

    output_dir = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "parametric_bracket"
        / "freecad"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating fixture in: {output_dir}")
    meta = create_bracket(output_dir)

    print(f"  FCStd: {meta['fcstd_path']}")
    print(f"  STEP:  {meta['step_path']}")
    print(f"  BasePlate Volume: {meta['objects']['BasePlate']['Volume_mm3']:.2f} mm³")
    print(f"  BasePlate Height (Thickness): {meta['objects']['BasePlate']['Height']} mm")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
