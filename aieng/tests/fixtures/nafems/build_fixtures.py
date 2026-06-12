"""NAFEMS-style V&V fixture builder.

Generates three linear-static reference cases as runnable ``.aieng`` packages:

* ``tension_rod``         — axial tension of a square rod.
* ``cantilever_end_load`` — end-loaded cantilever beam.
* ``cantilever_udl``      — uniformly distributed downward load on cantilever.

Each package contains the minimal artifacts required by
:mod:`aieng.simulation.deck_generator`:

* ``manifest.json``
* ``simulation/setup.yaml``
* ``simulation/cae_imports/source_solver_deck.inp``
* ``simulation/cae_mapping.json``

The mesh is a coarse C3D8 hexahedral grid that balances CI runtime against the
±10 % tolerance band documented in ``aieng/docs/nafems_vv_cases.md``.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

import yaml


# Shared material properties — steel.
STEEL = {
    "youngs_modulus_mpa": 210000.0,
    "poisson_ratio": 0.3,
    "density_kg_m3": 7850.0,
}

# Schema/format constants.
FORMAT_VERSION = "0.1.0"


def _build_manifest(model_id: str) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "format_version": FORMAT_VERSION,
        "units": {"length": "mm", "mass": "kg", "force": "N", "stress": "MPa"},
        "resources": {"simulation": {}, "results": {}},
        "created_by": {"tool": "nafems_fixture_builder", "created_at": "2026-01-01T00:00:00Z"},
    }


def _build_setup(
    *,
    bc_target_feature: str,
    load_target_feature: str,
    load_value_n: float,
    load_direction: list[int | float],
) -> dict[str, Any]:
    """Return a minimal setup.yaml for a single fixed-face + single-load case."""
    return {
        "materials": {"Steel": STEEL},
        "boundary_conditions": [
            {
                "id": "bc_fixed",
                "target_feature": bc_target_feature,
                "type": "fixed",
            },
        ],
        "loads": [
            {
                "id": "load_main",
                "target_feature": load_target_feature,
                "value_n": load_value_n,
                "direction": load_direction,
            },
        ],
    }


def _build_cae_mapping(*mappings: tuple[str, str]) -> dict[str, Any]:
    """Map feature IDs to NSET names in the source deck."""
    return {
        "mappings": [
            {"cae_entity": nset, "maps_to": {"feature_id": fid}}
            for nset, fid in mappings
        ],
    }


def _generate_hex_mesh(
    *,
    lx: float,
    ly: float,
    lz: float,
    nx: int,
    ny: int,
    nz: int,
) -> tuple[list[tuple[int, float, float, float]], list[tuple[int, int, int, int, int, int, int, int]], dict[str, set[int]]]:
    """Generate a structured hexahedral mesh for a rectangular prism.

    Returns ``(nodes, elements, nsets)`` where ``nsets`` keys are ``N_FIX``,
    ``N_LOAD``, and ``N_TOP`` (top face at Z=lz).
    """
    if nx <= 0 or ny <= 0 or nz <= 0:
        raise ValueError("element counts must be positive")

    dx, dy, dz = lx / nx, ly / ny, lz / nz

    nodes: list[tuple[int, float, float, float]] = []
    for k in range(nz + 1):
        z = k * dz
        for j in range(ny + 1):
            y = j * dy
            for i in range(nx + 1):
                x = i * dx
                nodes.append((len(nodes) + 1, x, y, z))

    node_id = lambda i, j, k: k * (nx + 1) * (ny + 1) + j * (nx + 1) + i + 1

    elements: list[tuple[int, int, int, int, int, int, int, int, int]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n1 = node_id(i, j, k)
                n2 = node_id(i + 1, j, k)
                n3 = node_id(i + 1, j + 1, k)
                n4 = node_id(i, j + 1, k)
                n5 = node_id(i, j, k + 1)
                n6 = node_id(i + 1, j, k + 1)
                n7 = node_id(i + 1, j + 1, k + 1)
                n8 = node_id(i, j + 1, k + 1)
                elements.append((len(elements) + 1, n1, n2, n3, n4, n5, n6, n7, n8))

    nsets: dict[str, set[int]] = {
        "N_FIX": set(),
        "N_LOAD": set(),
        "N_TOP": set(),
    }
    for nid, x, y, z in nodes:
        if math.isclose(x, 0.0, abs_tol=1e-9):
            nsets["N_FIX"].add(nid)
        if math.isclose(x, lx, abs_tol=1e-9):
            nsets["N_LOAD"].add(nid)
        if math.isclose(z, lz, abs_tol=1e-9):
            nsets["N_TOP"].add(nid)

    return nodes, elements, nsets


def _format_nset(name: str, node_ids: set[int], width: int = 16) -> list[str]:
    """Format a CalculiX *NSET block from a set of node IDs."""
    lines = [f"*NSET, NSET={name}"]
    ids = sorted(node_ids)
    for i in range(0, len(ids), width):
        lines.append(", ".join(str(nid) for nid in ids[i : i + width]))
    return lines


def _write_source_deck(
    *,
    nodes: list[tuple[int, float, float, float]],
    elements: list[tuple[int, int, int, int, int, int, int, int, int]],
    nsets: dict[str, set[int]],
    active_nsets: list[str],
) -> str:
    """Assemble a CalculiX-compatible source solver deck."""
    lines: list[str] = [
        "*NODE",
    ]
    for nid, x, y, z in nodes:
        lines.append(f"{nid}, {x:.6f}, {y:.6f}, {z:.6f}")

    lines.append("*ELEMENT, TYPE=C3D8, ELSET=EALL")
    for eid, n1, n2, n3, n4, n5, n6, n7, n8 in elements:
        lines.append(f"{eid}, {n1}, {n2}, {n3}, {n4}, {n5}, {n6}, {n7}, {n8}")

    for name in active_nsets:
        lines.extend(_format_nset(name, nsets[name]))

    lines.append("*ELSET, ELSET=EALL")
    lines.append(", ".join(str(eid) for eid, *_ in elements))

    lines.append("*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL")
    lines.append("1.0")
    return "\n".join(lines) + "\n"



def _build_package(
    out_path: Path,
    *,
    model_id: str,
    bc_target_feature: str,
    load_target_feature: str,
    load_value_n: float,
    load_direction: list[int | float],
    cae_mapping: dict[str, Any],
    source_deck: str,
) -> Path:
    """Write an ``.aieng`` package with the standard simulation artifacts."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    setup = _build_setup(
        bc_target_feature=bc_target_feature,
        load_target_feature=load_target_feature,
        load_value_n=load_value_n,
        load_direction=load_direction,
    )

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(_build_manifest(model_id), indent=2))
        zf.writestr("simulation/", b"")
        zf.writestr("simulation/cae_imports/", b"")
        zf.writestr("simulation/setup.yaml", yaml.safe_dump(setup))
        zf.writestr("simulation/cae_mapping.json", json.dumps(cae_mapping, indent=2))
        zf.writestr("simulation/cae_imports/source_solver_deck.inp", source_deck)

    return out_path


def build_tension_rod_fixture(out_path: Path | str) -> Path:
    """Build the ``tension_rod`` NAFEMS-style reference case."""
    out_path = Path(out_path)
    lx, ly, lz = 100.0, 10.0, 10.0
    nx, ny, nz = 20, 2, 2
    nodes, elements, nsets = _generate_hex_mesh(lx=lx, ly=ly, lz=lz, nx=nx, ny=ny, nz=nz)

    # Total 1000 N tensile load in +X on the X=L end face.
    load_face_nodes = len(nsets["N_LOAD"])
    load_per_node = 1000.0 / load_face_nodes

    source_deck = _write_source_deck(
        nodes=nodes,
        elements=elements,
        nsets=nsets,
        active_nsets=["N_FIX", "N_LOAD"],
    )

    return _build_package(
        out_path,
        model_id="nafems_tension_rod",
        bc_target_feature="feat_fix",
        load_target_feature="feat_load",
        load_value_n=load_per_node,
        load_direction=[1, 0, 0],
        cae_mapping=_build_cae_mapping(("N_FIX", "feat_fix"), ("N_LOAD", "feat_load")),
        source_deck=source_deck,
    )


def build_cantilever_end_load_fixture(out_path: Path | str) -> Path:
    """Build the ``cantilever_end_load`` NAFEMS-style reference case."""
    out_path = Path(out_path)
    lx, ly, lz = 100.0, 10.0, 20.0
    nx, ny, nz = 20, 4, 4
    nodes, elements, nsets = _generate_hex_mesh(lx=lx, ly=ly, lz=lz, nx=nx, ny=ny, nz=nz)

    # Total 100 N in -Z on the X=L end face.
    load_face_nodes = len(nsets["N_LOAD"])
    load_per_node = 100.0 / load_face_nodes

    source_deck = _write_source_deck(
        nodes=nodes,
        elements=elements,
        nsets=nsets,
        active_nsets=["N_FIX", "N_LOAD"],
    )

    return _build_package(
        out_path,
        model_id="nafems_cantilever_end_load",
        bc_target_feature="feat_fix",
        load_target_feature="feat_load",
        load_value_n=load_per_node,
        load_direction=[0, 0, -1],
        cae_mapping=_build_cae_mapping(("N_FIX", "feat_fix"), ("N_LOAD", "feat_load")),
        source_deck=source_deck,
    )


def build_cantilever_udl_fixture(out_path: Path | str) -> Path:
    """Build the ``cantilever_udl`` NAFEMS-style reference case."""
    out_path = Path(out_path)
    lx, ly, lz = 100.0, 10.0, 20.0
    nx, ny, nz = 20, 4, 4
    nodes, elements, nsets = _generate_hex_mesh(lx=lx, ly=ly, lz=lz, nx=nx, ny=ny, nz=nz)

    # Total 100 N distributed over all top-face (Z=lz) nodes.
    top_face_nodes = len(nsets["N_TOP"])
    load_per_node = 100.0 / top_face_nodes

    source_deck = _write_source_deck(
        nodes=nodes,
        elements=elements,
        nsets=nsets,
        active_nsets=["N_FIX", "N_TOP"],
    )

    return _build_package(
        out_path,
        model_id="nafems_cantilever_udl",
        bc_target_feature="feat_fix",
        load_target_feature="feat_top",
        load_value_n=load_per_node,
        load_direction=[0, 0, -1],
        cae_mapping=_build_cae_mapping(("N_FIX", "feat_fix"), ("N_TOP", "feat_top")),
        source_deck=source_deck,
    )


# Catalog of supported cases for runners/tests.
CASE_BUILDERS: dict[str, Any] = {
    "tension_rod": build_tension_rod_fixture,
    "cantilever_end_load": build_cantilever_end_load_fixture,
    "cantilever_udl": build_cantilever_udl_fixture,
}


def build_all_fixtures(out_dir: Path | str) -> dict[str, Path]:
    """Build all three NAFEMS-style fixtures into ``out_dir``.

    Returns a mapping from case_id to ``.aieng`` path.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        case_id: builder(out_dir / f"{case_id}.aieng")
        for case_id, builder in CASE_BUILDERS.items()
    }
