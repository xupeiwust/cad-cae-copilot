"""Declarative CAD skill template registry and code generator.

The registry loads YAML/JSON templates that describe reusable parametric
starter shapes.  Templates are validated at load time and translated into
build123d Python scripts that follow the same UPPER_SNAKE_CASE constant
convention used by the hand-written templates in ``cad_skill_planner.py``.

This keeps the existing Python templates first-class while allowing new
starter shapes to be added by dropping a YAML file into the registry
without redeploying backend code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

LOGGER = logging.getLogger(__name__)

SUPPORTED_PRIMITIVE_KINDS = {"box", "cylinder", "sphere", "revolve_profile"}
SUPPORTED_FEATURE_KINDS = {"hole", "hole_pattern", "fillet", "chamfer"}


class SkillTemplateError(Exception):
    """Raised when a template cannot be loaded or used."""

    def __init__(self, message: str, template_id: str | None = None) -> None:
        self.template_id = template_id
        prefix = f"Template '{template_id}': " if template_id else ""
        super().__init__(prefix + message)


class ParametricInput(BaseModel):
    """One editable parameter exposed as a UPPER_SNAKE_CASE constant."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    default: float
    min: float | None = None
    max: float | None = None
    unit: str = "mm"
    type: Literal["float", "int"] = "float"

    @field_validator("name")
    @classmethod
    def _name_is_snake_case(cls, value: str) -> str:
        if not value.replace("_", "").isalnum():
            raise ValueError("parameter name must be snake_case alphanumeric")
        return value


class BasePrimitive(BaseModel):
    """The starting solid for a template."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    label: str | None = None
    color: list[float] | None = Field(default=None, min_length=3, max_length=3)

    # box
    length: str | float | None = None
    width: str | float | None = None
    height: str | float | None = None

    # cylinder / sphere
    radius: str | float | None = None
    diameter: str | float | None = None
    height: str | float | None = None  # cylinder only

    # revolve_profile: list of [radius, z] points defining a closed X-Z profile
    profile: list[list[Any]] | None = None

    @field_validator("kind")
    @classmethod
    def _primitive_supported(cls, value: str) -> str:
        if value not in SUPPORTED_PRIMITIVE_KINDS:
            raise ValueError(
                f"unsupported primitive '{value}'; supported: {sorted(SUPPORTED_PRIMITIVE_KINDS)}"
            )
        return value


class FeatureOperation(BaseModel):
    """One operation applied to the base primitive."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)

    # hole / hole_pattern
    diameter: str | float | None = None
    depth: str | float | None = None

    # hole_pattern only
    pattern: Literal["polar", "grid"] | None = None
    count: int | None = None
    pitch_circle_diameter: str | float | None = None
    spacing_x: str | float | None = None
    spacing_y: str | float | None = None

    # fillet / chamfer
    radius: str | float | None = None
    length: str | float | None = None
    selector: str | None = None

    @field_validator("kind")
    @classmethod
    def _feature_supported(cls, value: str) -> str:
        if value not in SUPPORTED_FEATURE_KINDS:
            raise ValueError(
                f"unsupported feature '{value}'; supported: {sorted(SUPPORTED_FEATURE_KINDS)}"
            )
        return value


class FeatureGraphRule(BaseModel):
    """Hint telling the feature graph how to label a generated entity."""

    model_config = ConfigDict(extra="forbid")

    target: Literal["base_part", "feature"]
    label: str = Field(min_length=1)


class MateHint(BaseModel):
    """Optional assembly connection hint (advisory only)."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["mounting_face", "bolt_hole", "contact_face"]
    description: str = ""


class SkillTemplate(BaseModel):
    """A single declarative starter template."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    model_kind: Literal["mechanical", "organic"] = "mechanical"
    parametric_inputs: list[ParametricInput] = Field(default_factory=list)
    base_primitive: BasePrimitive
    features: list[FeatureOperation] = Field(default_factory=list)
    feature_graph_rules: list[FeatureGraphRule] = Field(default_factory=list)
    mate_hints: list[MateHint] = Field(default_factory=list)

    @field_validator("template_id")
    @classmethod
    def _template_id_safe(cls, value: str) -> str:
        if "/" in value or "\\" in value or ".." in value:
            raise ValueError("template_id must not contain path separators")
        return value


class SkillTemplateRegistry:
    """In-memory registry of declarative CAD starter templates."""

    def __init__(self, templates: dict[str, SkillTemplate]) -> None:
        self.templates = templates

    @classmethod
    def load(cls, directory: str | Path) -> "SkillTemplateRegistry":
        """Load and validate all ``*.yaml`` / ``*.yml`` / ``*.json`` files."""
        dir_path = Path(directory)
        templates: dict[str, SkillTemplate] = {}
        if not dir_path.exists():
            LOGGER.warning("Skill template directory does not exist: %s", dir_path)
            return cls(templates)

        for path in sorted(dir_path.iterdir()):
            if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            try:
                raw: Any = (
                    json.loads(path.read_text(encoding="utf-8"))
                    if path.suffix.lower() == ".json"
                    else yaml.safe_load(path.read_text(encoding="utf-8"))
                )
                if not isinstance(raw, dict):
                    raise SkillTemplateError(
                        f"{path.name}: root must be a mapping", template_id=None
                    )
                template = SkillTemplate.model_validate(raw)
            except ValidationError as exc:
                raise SkillTemplateError(
                    f"{path.name}: {exc.errors(include_url=False)}",
                    template_id=raw.get("template_id") if isinstance(raw, dict) else None,
                ) from exc
            except Exception as exc:
                raise SkillTemplateError(
                    f"{path.name}: {exc}", template_id=None
                ) from exc

            if template.template_id in templates:
                raise SkillTemplateError(
                    f"duplicate template_id '{template.template_id}'",
                    template_id=template.template_id,
                )
            templates[template.template_id] = template

        return cls(templates)

    def match(self, message: str) -> list[SkillTemplate]:
        """Return templates whose tags appear in the request text.

        Matches are returned in declaration order so deterministic tests stay
        stable.  Callers can pick the first match or disambiguate.
        """
        message_lower = message.lower()
        matched: list[SkillTemplate] = []
        for template in self.templates.values():
            tags = [t.lower() for t in ([template.template_id] + template.tags)]
            if any(tag in message_lower for tag in tags):
                matched.append(template)
        return matched

    def generate_plan(
        self,
        template: SkillTemplate,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve parameters and render the build123d execute_input.

        Returns a dict with both the ``execute_input`` block and the resolved
        numeric parameter values so callers can build assumptions / warnings
        without re-implementing parameter parsing.
        """
        params = _resolve_parameters(template, payload)
        code = _generate_build123d_code(template, params)
        name = template.name.format(**params)
        execute_input = {
            "name": name,
            "code": code,
            "mode": "replace",
            "model_kind": template.model_kind,
            "timeout": 60,
        }
        return {"execute_input": execute_input, "resolved_parameters": params}


def _resolve_parameters(
    template: SkillTemplate, payload: dict[str, Any]
) -> dict[str, float]:
    """Collect parameter values from payload overrides and template defaults."""
    resolved: dict[str, float] = {}
    for inp in template.parametric_inputs:
        key_mm = f"{inp.name}_mm"
        raw = payload.get(inp.name, payload.get(key_mm, inp.default))
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise SkillTemplateError(
                f"parameter '{inp.name}' must be numeric, got {raw!r}",
                template_id=template.template_id,
            ) from exc

        if inp.type == "int":
            value = int(value)
        else:
            value = float(value)

        if inp.min is not None and value < inp.min:
            raise SkillTemplateError(
                f"parameter '{inp.name}' value {value} is below minimum {inp.min}",
                template_id=template.template_id,
            )
        if inp.max is not None and value > inp.max:
            raise SkillTemplateError(
                f"parameter '{inp.name}' value {value} is above maximum {inp.max}",
                template_id=template.template_id,
            )
        resolved[inp.name] = value
    return resolved


def _expr(value: str | float | int | None) -> str:
    """Return a Python expression string for a numeric or expression value."""
    if value is None:
        return "0.0"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return str(value)


def _generate_build123d_code(
    template: SkillTemplate, params: dict[str, float]
) -> str:
    """Render a complete build123d script from a validated template."""
    lines: list[str] = ["from build123d import *", ""]

    for name, value in params.items():
        lines.append(f"{name.upper()} = {value:.3f}")
    lines.append("")

    lines.append("with BuildPart() as _template_bp:")
    _emit_primitive(lines, template.base_primitive, 1)
    for feature in template.features:
        _emit_feature(lines, feature, 1)
    lines.append("")

    base_label = template.base_primitive.label or template.template_id
    rule_label = next(
        (rule.label for rule in template.feature_graph_rules if rule.target == "base_part"),
        None,
    )
    final_label = rule_label or base_label

    lines.append("_part = _template_bp.part")
    lines.append(f'_part.label = "{final_label}"')
    if template.base_primitive.color:
        c = template.base_primitive.color
        lines.append(f"_part.color = Color({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f})")

    lines.append("")
    lines.append("result = Compound(children=[_part])")
    return "\n".join(lines)


def _emit_primitive(
    lines: list[str], primitive: BasePrimitive, indent_level: int
) -> None:
    indent = "    " * indent_level
    kind = primitive.kind

    if kind == "box":
        lines.append(
            f"{indent}Box({_expr(primitive.length)}, {_expr(primitive.width)}, "
            f"{_expr(primitive.height)}, align=(Align.CENTER, Align.CENTER, Align.MIN))"
        )
    elif kind == "cylinder":
        radius = (
            _expr(primitive.radius)
            if primitive.radius is not None
            else f"({_expr(primitive.diameter)} / 2)"
        )
        lines.append(
            f"{indent}Cylinder(radius={radius}, height={_expr(primitive.height)}, "
            "align=(Align.CENTER, Align.CENTER, Align.MIN))"
        )
    elif kind == "sphere":
        radius = _expr(primitive.radius)
        lines.append(f"{indent}Sphere(radius={radius})")
    elif kind == "revolve_profile":
        if not primitive.profile:
            raise SkillTemplateError(
                "revolve_profile requires a non-empty 'profile' list", template_id=None
            )
        pts = []
        for point in primitive.profile:
            if len(point) != 2:
                raise SkillTemplateError(
                    "revolve_profile profile points must be [radius, z]",
                    template_id=None,
                )
            pts.append(f"({_expr(point[0])}, {_expr(point[1])})")
        lines.append(f"{indent}with BuildSketch(Plane.XZ):")
        lines.append(f"{indent}    with BuildLine():")
        lines.append(f"{indent}        Polyline({', '.join(pts)}, close=True)")
        lines.append(f"{indent}    make_face()")
        lines.append(f"{indent}revolve(axis=Axis.Z)")
    else:
        raise SkillTemplateError(
            f"unsupported primitive '{kind}'", template_id=None
        )


def _emit_feature(lines: list[str], feature: FeatureOperation, indent_level: int) -> None:
    indent = "    " * indent_level
    kind = feature.kind

    if kind == "hole":
        lines.append(f"{indent}with Locations((0, 0, 0)):")
        lines.append(
            f"{indent}    Hole(radius={_expr(feature.diameter)} / 2, "
            f"depth={_expr(feature.depth)})"
        )
    elif kind == "hole_pattern":
        if feature.pattern == "polar":
            lines.append(
                f"{indent}with PolarLocations(radius={_expr(feature.pitch_circle_diameter)} / 2, "
                f"count={feature.count}):"
            )
            lines.append(
                f"{indent}    Hole(radius={_expr(feature.diameter)} / 2, "
                f"depth={_expr(feature.depth)})"
            )
        elif feature.pattern == "grid":
            lines.append(
                f"{indent}with GridLocations("
                f"x_spacing={_expr(feature.spacing_x)}, "
                f"y_spacing={_expr(feature.spacing_y)}, "
                f"x_count={feature.count}, y_count=1):"
            )
            lines.append(
                f"{indent}    Hole(radius={_expr(feature.diameter)} / 2, "
                f"depth={_expr(feature.depth)})"
            )
        else:
            raise SkillTemplateError(
                f"hole_pattern requires 'polar' or 'grid', got {feature.pattern!r}",
                template_id=None,
            )
    elif kind == "fillet":
        selector = feature.selector or "_template_bp.edges().filter_by(Axis.Z)"
        lines.append(
            f"{indent}try:\n{indent}    fillet({selector}, radius={_expr(feature.radius)})\n"
            f"{indent}except Exception:\n{indent}    pass"
        )
    elif kind == "chamfer":
        selector = feature.selector or "_template_bp.edges().filter_by(Axis.Z)"
        lines.append(
            f"{indent}try:\n{indent}    chamfer({selector}, length={_expr(feature.length)})\n"
            f"{indent}except Exception:\n{indent}    pass"
        )
    else:
        raise SkillTemplateError(
            f"unsupported feature '{kind}'", template_id=None
        )


def default_template_directory() -> Path:
    """Return the built-in skill template directory."""
    return Path(__file__).with_suffix("").parent / "data" / "skill_templates"
