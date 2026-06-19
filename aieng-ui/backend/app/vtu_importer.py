"""VTU (VTK UnstructuredGrid) result importer (#279 D1/D2).

Parses inline ASCII and uncompressed inline base64-binary ``.vtu`` files so the
viewer can display a scalar field from a second solver (Code_Aster / ParaView /
ElmerFEM all export VTU) via the same ``/api/projects/{id}/fields/{name}`` path
used for CalculiX FRD.

Honest boundary: only inline ``DataArray`` payloads are supported. Appended data
and compressed payloads are reported unavailable rather than mis-parsed — never
guessed.
"""

from __future__ import annotations

import base64
import math
import struct
import zipfile
from pathlib import Path
from typing import Any

try:  # Packaged installs use the hardened parser declared in pyproject.toml.
    import defusedxml.ElementTree as ET
except ModuleNotFoundError:  # pragma: no cover - local dev env without optional reinstall
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]

# Canonical field name -> candidate VTU PointData array names (case-insensitive).
# Vector arrays (num_components == 3) are reduced to per-node magnitude for the
# magnitude/displacement fields.
_FIELD_ARRAY_ALIASES: dict[str, tuple[str, ...]] = {
    "von_mises": ("von_mises", "vonmises", "s_mises", "mises", "vm", "sigma_vm"),
    "disp_magnitude": ("disp_magnitude", "displacement", "u", "umag", "disp"),
    "displacement": ("displacement", "disp_magnitude", "u", "umag", "disp"),
}
_VECTOR_MAGNITUDE_FIELDS = {"disp_magnitude", "displacement"}

_FIELD_UNITS: dict[str, str] = {
    "von_mises": "MPa",
    "disp_magnitude": "mm",
    "displacement": "mm",
}

# Candidate member paths for a VTU result inside a .aieng package.
_VTU_MEMBER_SUFFIXES = ("/outputs/result.vtu", "simulation/result.vtu", "result.vtu")

_VTK_STRUCT_TYPES: dict[str, tuple[str, int]] = {
    "Float32": ("f", 4),
    "Float64": ("d", 8),
    "Int32": ("i", 4),
    "Int64": ("q", 8),
    "UInt8": ("B", 1),
    "UInt32": ("I", 4),
    "UInt64": ("Q", 8),
}


def parse_vtu(content: str | bytes) -> dict[str, Any]:
    """Parse an inline ASCII or inline binary VTU document into points + point-data arrays.

    Returns ``{available, points, point_data}`` where ``points`` is a list of
    ``(x, y, z)`` tuples and ``point_data`` maps each array name to
    ``{values: [...], num_components: int}``. On any unsupported encoding or parse
    error returns ``{available: False, reason: ...}`` (never raises).
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    try:
        root = ET.fromstring(content)
    except Exception as exc:
        return {"available": False, "reason": f"VTU XML parse error: {exc}"}

    if root.get("compressor"):
        return {"available": False, "reason": "Compressed VTU DataArrays are not supported."}
    byte_order = _byte_order_prefix(root.get("byte_order"))
    header_type = root.get("header_type") or "UInt32"

    grid = root.find(".//UnstructuredGrid")
    if grid is None:
        return {"available": False, "reason": "No UnstructuredGrid element found."}
    piece = grid.find("Piece")
    if piece is None:
        return {"available": False, "reason": "No Piece element found."}

    # Points
    points_elem = piece.find("Points/DataArray")
    if points_elem is None:
        return {"available": False, "reason": "No Points DataArray found."}
    flat = _parse_numeric_array(points_elem, byte_order=byte_order, header_type=header_type)
    if flat is None:
        return {
            "available": False,
            "reason": "Unsupported VTU Points DataArray payload (got "
            f"format={points_elem.get('format')!r}).",
        }
    points = [tuple(flat[i : i + 3]) for i in range(0, len(flat) - len(flat) % 3, 3)]

    # PointData arrays
    point_data: dict[str, dict[str, Any]] = {}
    pd = piece.find("PointData")
    for arr in pd.findall("DataArray") if pd is not None else []:
        name = arr.get("Name")
        if not name:
            continue
        ncomp = _parse_positive_int(arr.get("NumberOfComponents", "1") or "1")
        if ncomp is None:
            continue
        values = _parse_numeric_array(arr, byte_order=byte_order, header_type=header_type)
        if values is None:
            continue
        point_data[name] = {"values": values, "num_components": ncomp}

    return {"available": True, "points": points, "point_data": point_data}


def _parse_numeric_array(elem: ET.Element, *, byte_order: str, header_type: str) -> list[float] | None:
    fmt = (elem.get("format") or "ascii").strip().lower()
    if fmt == "ascii":
        return _parse_floats(elem.text) if (elem.text or "").strip() else None
    if fmt == "binary":
        return _parse_binary_numeric_array(elem, byte_order=byte_order, header_type=header_type)
    return None


def _byte_order_prefix(value: str | None) -> str:
    return ">" if str(value or "").lower() == "bigendian" else "<"


def _parse_binary_numeric_array(elem: ET.Element, *, byte_order: str, header_type: str) -> list[float] | None:
    vtk_type = elem.get("type") or "Float64"
    type_info = _VTK_STRUCT_TYPES.get(vtk_type)
    header_info = _VTK_STRUCT_TYPES.get(header_type)
    text = (elem.text or "").strip()
    if type_info is None or header_info is None or not text:
        return None
    try:
        blob = base64.b64decode(text, validate=True)
    except Exception:
        return None
    header_code, header_size = header_info
    if len(blob) < header_size:
        return None
    try:
        (payload_size,) = struct.unpack(f"{byte_order}{header_code}", blob[:header_size])
    except struct.error:
        return None
    if header_size + payload_size > len(blob):
        return None
    payload = blob[header_size : header_size + payload_size]
    value_code, value_size = type_info
    if len(payload) % value_size:
        return None
    count = len(payload) // value_size
    if count == 0:
        return []
    try:
        return [float(v) for v in struct.unpack(f"{byte_order}{count}{value_code}", payload)]
    except struct.error:
        return None


def _parse_floats(text: str | None) -> list[float]:
    if not text:
        return []
    out: list[float] = []
    for tok in text.split():
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out


def _parse_positive_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _resolve_field_array(
    point_data: dict[str, dict[str, Any]], field_name: str
) -> dict[str, Any] | None:
    """Resolve a canonical field name to a VTU PointData array (case-insensitive)."""
    lower_index = {name.lower(): name for name in point_data}
    candidates = _FIELD_ARRAY_ALIASES.get(field_name, (field_name,))
    for cand in candidates:
        actual = lower_index.get(cand.lower())
        if actual is not None:
            return point_data[actual]
    return None


def _read_vtu_member(package_path: Path) -> str | None:
    """Return the newest VTU member text inside a .aieng package, or None."""
    if not package_path.exists():
        return None
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = zf.namelist()
            matches = [
                n for n in names if any(n.endswith(sfx) for sfx in _VTU_MEMBER_SUFFIXES)
            ]
            if not matches:
                return None
            # Prefer the lexicographically last run (run_002 > run_001).
            chosen = sorted(matches)[-1]
            return zf.read(chosen).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError):
        return None


def extract_vtu_field(package_path: str | Path, field_name: str) -> dict[str, Any] | None:
    """Extract a per-node scalar field + coordinates from a VTU inside a package.

    Returns the same shape the FRD extractor produces (``values``, ``node_coords``,
    ``min_value``, ``max_value``, ``unit``, ``warnings``) plus ``source: "vtu"``, or
    ``None`` when no VTU exists or the field is absent. Vector arrays are reduced to
    per-node magnitude for displacement/magnitude fields.
    """
    package_path = Path(package_path)
    text = _read_vtu_member(package_path)
    if text is None:
        return None

    parsed = parse_vtu(text)
    if not parsed.get("available"):
        return None

    array = _resolve_field_array(parsed["point_data"], field_name)
    if array is None:
        return None

    raw = array["values"]
    ncomp = array["num_components"]
    if ncomp == 3 and field_name in _VECTOR_MAGNITUDE_FIELDS:
        values = [
            math.sqrt(raw[i] ** 2 + raw[i + 1] ** 2 + raw[i + 2] ** 2)
            for i in range(0, len(raw) - len(raw) % 3, 3)
        ]
    elif ncomp == 1:
        values = list(raw)
    else:
        # A multi-component array requested as a scalar isn't meaningful here.
        return None

    if not values:
        return None

    points = parsed["points"]
    warnings: list[str] = []
    if len(points) != len(values):
        warnings.append(
            f"VTU point count ({len(points)}) != value count ({len(values)}); "
            "coordinates and values may be misaligned."
        )

    return {
        "values": [round(v, 6) for v in values],
        "node_coords": [list(p) for p in points],
        "min_value": round(min(values), 6),
        "max_value": round(max(values), 6),
        "unit": _FIELD_UNITS.get(field_name, ""),
        "warnings": warnings,
        "source": "vtu",
    }
