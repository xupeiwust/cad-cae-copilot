"""Generate a deterministic minimal sample FCStd file for Phase 20 tests/demos.

FreeCAD `.FCStd` files are zip archives. The minimum content needed for the
reference converter is a `Document.xml` describing a small set of objects
with named properties. This script writes such an archive to
`examples/sample_bracket.FCStd` (or wherever ``--out`` points).

The fixture is intentionally synthetic: it is built from a static XML
template and does not require FreeCAD to be installed.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


DOCUMENT_XML = """<?xml version='1.0' encoding='utf-8'?>
<!-- Synthetic FCStd fixture for .aieng Phase 20 converter tests. -->
<Document SchemaVersion="4" ProgramVersion="0.21" FileVersion="1">
    <Properties Count="0"></Properties>
    <Objects Count="4">
        <Object type="Part::Box" name="Plate" id="1"/>
        <Object type="PartDesign::Hole" name="MountingHole_1" id="2"/>
        <Object type="PartDesign::Hole" name="MountingHole_2" id="3"/>
        <Object type="PartDesign::Pad" name="Flange_Top" id="4"/>
    </Objects>
    <ObjectData Count="4">
        <Object name="Plate">
            <Properties Count="4">
                <Property name="Length" type="App::PropertyLength">
                    <Float value="100.0"/>
                </Property>
                <Property name="Width" type="App::PropertyLength">
                    <Float value="50.0"/>
                </Property>
                <Property name="Height" type="App::PropertyLength">
                    <Float value="10.0"/>
                </Property>
                <Property name="Label" type="App::PropertyString">
                    <String value="Base plate"/>
                </Property>
            </Properties>
        </Object>
        <Object name="MountingHole_1">
            <Properties Count="2">
                <Property name="Diameter" type="App::PropertyLength">
                    <Float value="6.0"/>
                </Property>
                <Property name="Depth" type="App::PropertyLength">
                    <Float value="10.0"/>
                </Property>
            </Properties>
        </Object>
        <Object name="MountingHole_2">
            <Properties Count="2">
                <Property name="Diameter" type="App::PropertyLength">
                    <Float value="6.0"/>
                </Property>
                <Property name="Depth" type="App::PropertyLength">
                    <Float value="10.0"/>
                </Property>
            </Properties>
        </Object>
        <Object name="Flange_Top">
            <Properties Count="2">
                <Property name="Length" type="App::PropertyLength">
                    <Float value="40.0"/>
                </Property>
                <Property name="Width" type="App::PropertyLength">
                    <Float value="20.0"/>
                </Property>
            </Properties>
        </Object>
    </ObjectData>
</Document>
"""


GUI_DOCUMENT_XML = """<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="1">
    <ViewProviderData Count="0"></ViewProviderData>
</Document>
"""


def generate(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Document.xml", DOCUMENT_XML)
        archive.writestr("GuiDocument.xml", GUI_DOCUMENT_XML)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic FCStd fixture")
    parser.add_argument(
        "--out",
        default="examples/sample_bracket.FCStd",
        help="Output FCStd path (default: examples/sample_bracket.FCStd)",
    )
    args = parser.parse_args()
    written = generate(Path(args.out))
    print(f"PASS wrote sample FCStd -> {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
