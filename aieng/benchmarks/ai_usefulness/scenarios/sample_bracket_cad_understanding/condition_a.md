# Condition A — Raw FCStd Source

**Instructions for the evaluator**: Provide the text in the section below to the AI as its
entire input. Do not provide any `.aieng` resources, JSON, or additional context.

**Instructions for the AI**: Below is the `Document.xml` extracted from a FreeCAD `.FCStd`
file for a mechanical bracket assembly. Answer the benchmark questions based only on
this information.

---

## FreeCAD Document.xml

```xml
<?xml version='1.0' encoding='utf-8'?>
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
```

---

## Context note (provided to AI)

This is a FreeCAD parametric model. The `Objects` block lists all model objects with
their types. The `ObjectData` block lists their properties. No geometry kernel, mesh,
solver output, or simulation setup is included.

Source: `examples/sample_bracket.FCStd` from the `.aieng` project.
