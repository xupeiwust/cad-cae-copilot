"""Topology optimization — contract + pluggable optimizer registry.

Topology optimization is a CAE-driven *generative* step that sits after analysis:
given a design space, load/support boundary conditions, and a volume budget, it
finds where material should be. Like solvers, the optimizer is a **pluggable
backend** behind a neutral contract — the built-in reference is a self-contained
2D SIMP (compliance minimization, pure numpy, no external solver/dependency).
Other optimizers (3D SIMP, ToPy, nTop, remote) can register and emit the same
neutral result.

Output: ``analysis/topology_optimization.json`` (optimizer provenance, objective
history, achieved volume fraction, density grid, honest limitations). The result is
also authored back into a Shape IR representation (``topology_result_to_shape_ir`` /
``write_shape_ir_from_topology_optimization``): the density field becomes one
``density_voxels`` node that the existing compilers expand into extruded voxel
geometry, so the optimized body re-compiles, meshes, and views like any other Shape
IR — and stays linked to its ``design_space_node``.

The problem itself can be DERIVED from the project's real CAE intent rather than a
preset: ``derive_topopt_problem_from_package`` reads the design-space bbox + face
geometry + supports/loads and projects them onto a 2D plane (the two largest
design-space dims) as explicit cell-based ``bcs.supports``/``bcs.loads``, which
``simp_2d`` consumes directly.

Honest scope of the built-in optimizer: 2D, plane-stress, linear-elastic, single
isotropic material, regular grid, coarse; 3D supports/loads are projected to the
plane and out-of-plane force is dropped. It is an observational design aid, not a
production optimizer.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from aieng import FORMAT_VERSION
from aieng.converters.shape_ir import _AXIS_INDEX

TOPOLOGY_OPTIMIZATION_PATH = "analysis/topology_optimization.json"
TOPOPT_CONTRACT_VERSION = "0.1"

_OPTIMIZER_REGISTRY: dict[str, dict[str, Any]] = {}


def register_optimizer(name: str, fn: Callable[[dict[str, Any]], dict[str, Any]], *,
                       version: str = "0.1", method: str = "", dimension: int = 0) -> None:
    """Register an optimizer. ``fn(problem) -> optimizer_result`` dict."""
    _OPTIMIZER_REGISTRY[name] = {"fn": fn, "version": version, "method": method, "dimension": dimension}


def available_optimizers() -> list[str]:
    return sorted(_OPTIMIZER_REGISTRY)


# ── 2D SIMP (self-contained reference optimizer) ─────────────────────────────

def _element_stiffness() -> np.ndarray:
    """8x8 element stiffness for a unit bilinear quad, plane stress, E=1, nu=0.3."""
    nu = 0.3
    k = np.array([
        1 / 2 - nu / 6, 1 / 8 + nu / 8, -1 / 4 - nu / 12, -1 / 8 + 3 * nu / 8,
        -1 / 4 + nu / 12, -1 / 8 - nu / 8, nu / 6, 1 / 8 - 3 * nu / 8,
    ])
    KE = 1 / (1 - nu ** 2) * np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
    ])
    return KE


def _boundary_conditions(nelx: int, nely: int, preset: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (fixed_dofs, force_vector) for a preset. 0-based dofs; 2 per node;
    node index = (nely+1)*elx + ely; dof = 2*node (x), 2*node+1 (y)."""
    ndof = 2 * (nelx + 1) * (nely + 1)
    F = np.zeros(ndof)

    def node(elx: int, ely: int) -> int:
        return (nely + 1) * elx + ely

    preset = (preset or "cantilever").lower()
    if preset == "mbb_beam":
        # left edge: x fixed; bottom-right corner: y fixed (roller); load down at top-left
        fixed = [2 * node(0, ely) for ely in range(nely + 1)]
        fixed.append(2 * node(nelx, nely) + 1)
        F[2 * node(0, 0) + 1] = -1.0
    else:  # cantilever (default): left edge fully clamped, downward tip load at right-middle
        fixed = []
        for ely in range(nely + 1):
            fixed.append(2 * node(0, ely))
            fixed.append(2 * node(0, ely) + 1)
        F[2 * node(nelx, nely // 2) + 1] = -1.0
    return np.array(sorted(set(fixed)), dtype=int), F


def _explicit_bcs(nelx: int, nely: int, supports: list, loads: list) -> tuple[np.ndarray, np.ndarray]:
    """Build (fixed_dofs, force_vector) from explicit cell-based BCs.

    A support/load entry carries ``cells`` = list of ``[i, j]`` (i = column = elx,
    j = row = ely). Support cells clamp both dofs of their 4 corner nodes; load
    cells distribute ``(fx, fy)`` evenly over the union of their corner nodes.
    This is what a derived problem (from real CAE supports/loads) feeds in instead
    of a preset.
    """
    ndof = 2 * (nelx + 1) * (nely + 1)
    F = np.zeros(ndof)

    def node(elx: int, ely: int) -> int:
        return (nely + 1) * elx + ely

    def corners(i: int, j: int) -> list[int]:
        i = min(max(int(i), 0), nelx - 1)
        j = min(max(int(j), 0), nely - 1)
        return [node(i, j), node(i + 1, j), node(i, j + 1), node(i + 1, j + 1)]

    fixed: set[int] = set()
    for s in supports or []:
        for cell in s.get("cells", []):
            for n in corners(cell[0], cell[1]):
                fixed.add(2 * n)
                fixed.add(2 * n + 1)

    for ld in loads or []:
        fx = float(ld.get("fx", 0.0))
        fy = float(ld.get("fy", 0.0))
        nodes: set[int] = set()
        for cell in ld.get("cells", []):
            nodes.update(corners(cell[0], cell[1]))
        if nodes and (fx or fy):
            per = 1.0 / len(nodes)
            for n in nodes:
                F[2 * n] += fx * per
                F[2 * n + 1] += fy * per

    return np.array(sorted(fixed), dtype=int), F


def _resolve_bcs(nelx: int, nely: int, bcs: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, str | None]:
    """Explicit supports/loads if present, else a named preset. Returns
    (fixed_dofs, force_vector, preset_name) — preset_name is None when explicit."""
    supports = bcs.get("supports")
    loads = bcs.get("loads")
    if supports or loads:
        fixed, F = _explicit_bcs(nelx, nely, supports or [], loads or [])
        if fixed.size and np.abs(F).sum() > 0:
            return fixed, F, None
        # degenerate explicit BCs (no support or no load) -> fall back to a preset
    preset = str(bcs.get("preset") or "cantilever")
    fixed, F = _boundary_conditions(nelx, nely, preset)
    return fixed, F, preset


def simp_2d(problem: dict[str, Any]) -> dict[str, Any]:
    """Classic 2D SIMP compliance minimization (OC update + sensitivity filter).

    problem.grid = {nelx, nely}; volfrac, penalty (default 3), rmin (default 1.5),
    max_iters (default 40), bcs.preset ('cantilever'|'mbb_beam'). Pure numpy
    (dense FE solve) — suitable for small/coarse design domains.
    """
    grid = problem.get("grid") or {}
    nelx = int(grid.get("nelx", 30))
    nely = int(grid.get("nely", 10))
    volfrac = float(problem.get("volfrac", 0.5))
    penal = float(problem.get("penalty", 3.0))
    rmin = float(problem.get("rmin", 1.5))
    max_iters = int(problem.get("max_iters", 40))
    bcs = problem.get("bcs") or {}

    KE = _element_stiffness()
    ndof = 2 * (nelx + 1) * (nely + 1)
    fixed, F, preset = _resolve_bcs(nelx, nely, bcs)
    bcs_source = "preset" if preset is not None else "explicit"
    free = np.setdiff1d(np.arange(ndof), fixed)

    # element -> global dof map
    edof = np.zeros((nelx * nely, 8), dtype=int)
    for elx in range(nelx):
        for ely in range(nely):
            n1 = (nely + 1) * elx + ely
            n2 = (nely + 1) * (elx + 1) + ely
            e = elx * nely + ely
            edof[e] = [2 * n1, 2 * n1 + 1, 2 * n2, 2 * n2 + 1, 2 * n2 + 2, 2 * n2 + 3, 2 * n1 + 2, 2 * n1 + 3]

    # sensitivity filter weights (precomputed)
    x = np.full((nely, nelx), volfrac)
    ceil_r = int(np.ceil(rmin))
    history: list[float] = []
    change = 1.0
    it = 0
    while change > 0.01 and it < max_iters:
        it += 1
        # FE analysis (dense solve on free dofs)
        K = np.zeros((ndof, ndof))
        xpen = x ** penal
        for elx in range(nelx):
            for ely in range(nely):
                e = elx * nely + ely
                ed = edof[e]
                K[np.ix_(ed, ed)] += xpen[ely, elx] * KE
        U = np.zeros(ndof)
        U[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])

        # compliance + sensitivities
        c = 0.0
        dc = np.zeros((nely, nelx))
        for elx in range(nelx):
            for ely in range(nely):
                e = elx * nely + ely
                ue = U[edof[e]]
                ke_energy = float(ue @ KE @ ue)
                c += xpen[ely, elx] * ke_energy
                dc[ely, elx] = -penal * (x[ely, elx] ** (penal - 1)) * ke_energy
        history.append(round(c, 6))

        # sensitivity filtering
        dcf = np.zeros((nely, nelx))
        for i in range(nelx):
            for j in range(nely):
                s = 0.0
                acc = 0.0
                for k in range(max(i - ceil_r, 0), min(i + ceil_r + 1, nelx)):
                    for l in range(max(j - ceil_r, 0), min(j + ceil_r + 1, nely)):
                        fac = rmin - np.hypot(i - k, j - l)
                        if fac > 0:
                            s += fac
                            acc += fac * x[l, k] * dc[l, k]
                dcf[j, i] = acc / (x[j, i] * s) if s > 0 else dc[j, i]

        # optimality-criteria update with bisection on the volume multiplier
        l1, l2, move = 1e-9, 1e9, 0.2
        xnew = x.copy()
        while (l2 - l1) / (l1 + l2) > 1e-3:
            lmid = 0.5 * (l1 + l2)
            xnew = np.clip(
                x * np.sqrt(np.maximum(-dcf, 0) / lmid),
                np.maximum(x - move, 0.001),
                np.minimum(x + move, 1.0),
            )
            if xnew.mean() - volfrac > 0:
                l1 = lmid
            else:
                l2 = lmid
        change = float(np.abs(xnew - x).max())
        x = xnew

    return {
        "density": [[round(float(v), 4) for v in row] for row in x.tolist()],
        "nelx": nelx, "nely": nely,
        "iterations": it,
        "compliance_history": history,
        "final_compliance": history[-1] if history else None,
        "achieved_volume_fraction": round(float(x.mean()), 4),
        "target_volume_fraction": volfrac,
        "bcs_preset": preset,
        "bcs_source": bcs_source,
    }


def precomputed_optimizer(problem: dict[str, Any]) -> dict[str, Any]:
    """Fake optimizer: ingests a precomputed density grid (problem['density']).
    Proves the optimizer layer is neutral — no solve is performed."""
    density = problem.get("density")
    if not (isinstance(density, list) and density and isinstance(density[0], list)):
        raise ValueError("precomputed optimizer requires problem['density'] as a 2D grid")
    nely = len(density)
    nelx = len(density[0])
    mean = float(np.mean(np.asarray(density, dtype=float)))
    return {
        "density": [[round(float(v), 4) for v in row] for row in density],
        "nelx": nelx, "nely": nely,
        "iterations": 0,
        "compliance_history": list(problem.get("compliance_history") or []),
        "final_compliance": problem.get("final_compliance"),
        "achieved_volume_fraction": round(mean, 4),
        "target_volume_fraction": problem.get("volfrac", round(mean, 4)),
        "bcs_preset": (problem.get("bcs") or {}).get("preset"),
    }


register_optimizer("simp_2d", simp_2d, version="0.1", method="SIMP", dimension=2)
register_optimizer("precomputed", precomputed_optimizer, version="0.1", method="precomputed", dimension=2)


# ── derive a problem from a project's CAE setup + geometry ───────────────────
# Connects "design space / supports / loads" (the project's real CAE intent) to
# the topology-optimization problem, instead of a hand-picked preset. The built-in
# optimizer is 2D, so 3D supports/loads are PROJECTED onto the plane of the two
# largest design-space dimensions; out-of-plane components are dropped (plane
# stress). This is honest 3D→2D — the projection + dropped components are recorded
# in the returned `derivation` block, and missing/degenerate data falls back to a
# preset with a warning rather than producing a silently-wrong problem.

def _read_member_text(zf: zipfile.ZipFile, name: str) -> str | None:
    try:
        return zf.read(name).decode("utf-8")
    except KeyError:
        return None


def _load_cae_setup(zf: zipfile.ZipFile) -> dict[str, Any]:
    """CAE setup from simulation/setup.yaml (active) or a JSON setup, else {}."""
    raw = (
        _read_member_text(zf, "simulation/setup.yaml")
        or _read_member_text(zf, "simulation/setup.json")
        or _read_member_text(zf, "cae/setup.json")
    )
    if not raw:
        return {}
    if raw.lstrip().startswith("{"):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    try:
        import yaml  # lazy: only needed for YAML setups
        return yaml.safe_load(raw) or {}
    except Exception:
        return {}


def _bbox_center(bbox: Any) -> list[float] | None:
    if not (isinstance(bbox, list) and len(bbox) >= 6):
        return None
    return [(bbox[0] + bbox[3]) / 2.0, (bbox[1] + bbox[4]) / 2.0, (bbox[2] + bbox[5]) / 2.0]


def _topology_entities(topology_map: Any) -> list[dict[str, Any]]:
    if isinstance(topology_map, list):
        return [e for e in topology_map if isinstance(e, dict)]
    if isinstance(topology_map, dict):
        ents = topology_map.get("entities") or topology_map.get("topology") or []
        return [e for e in ents if isinstance(e, dict)]
    return []


def _index_faces(topology_map: Any) -> tuple[dict[str, dict[str, Any]], list[float] | None, str | None]:
    """Return (faces_by_id, overall_bbox, largest_solid_source_node)."""
    faces: dict[str, dict[str, Any]] = {}
    union: list[float] | None = None
    best_solid: tuple[float, str] | None = None  # (volume, source_node)
    overall: list[float] | None = None
    for ent in _topology_entities(topology_map):
        et = str(ent.get("type") or "").lower()
        bb = ent.get("bounding_box") or ent.get("bbox")
        if isinstance(bb, list) and len(bb) >= 6:
            union = list(bb) if union is None else (
                [min(union[k], bb[k]) for k in range(3)] + [max(union[k + 3], bb[k + 3]) for k in range(3)]
            )
        if et == "face" and ent.get("id") is not None:
            faces[str(ent["id"])] = {
                "bbox": bb,
                "normal": ent.get("normal") or ent.get("proxy_normal"),
                "center": ent.get("center") or _bbox_center(bb),
            }
        if et in {"solid", "body"} and isinstance(bb, list) and len(bb) >= 6:
            vol = max(bb[3] - bb[0], 0) * max(bb[4] - bb[1], 0) * max(bb[5] - bb[2], 0)
            node = str(ent.get("source_ir_node") or ent.get("name") or ent.get("id") or "")
            if best_solid is None or vol > best_solid[0]:
                best_solid = (vol, node)
                overall = list(bb)
    return faces, (overall or union), (best_solid[1] if best_solid else None)


def _feature_to_faces(cae_mapping: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for m in (cae_mapping or {}).get("mappings", []) or []:
        fid = (m.get("maps_to") or {}).get("feature_id")
        if fid:
            out[str(fid)] = [str(x) for x in (m.get("face_ids") or [])]
    return out


def _resolve_target_faces(target: Any, feat_to_faces: dict[str, list[str]], faces: dict[str, Any]) -> list[str]:
    t = str(target or "")
    if t in feat_to_faces:
        return [f for f in feat_to_faces[t] if f in faces]
    if t in faces:  # target is itself a face id
        return [t]
    if f"face_{t}" in faces:
        return [f"face_{t}"]
    return []


def _dedup_cells(cells: list[list[int]]) -> list[list[int]]:
    seen: set[tuple[int, int]] = set()
    out: list[list[int]] = []
    for c in cells:
        key = (int(c[0]), int(c[1]))
        if key not in seen:
            seen.add(key)
            out.append([key[0], key[1]])
    return out


def derive_topopt_problem_from_package(
    package_path: str | Path, *,
    resolution: int = 48, volfrac: float = 0.5, penalty: float = 3.0,
    rmin: float = 1.5, max_iters: int = 40, objective: str = "compliance_minimization",
) -> dict[str, Any]:
    """Derive a 2D topology-optimization problem from a project's CAE setup + geometry.

    Reads geometry/topology_map.json (design-space bbox + face geometry),
    simulation/cae_mapping.json (feature→face links) and the CAE setup
    (supports + loads). Projects the supports/loads onto the plane of the two
    largest design-space dimensions and maps them to grid cells, returning a
    ``problem`` with explicit ``bcs.supports``/``bcs.loads``. The ``derivation``
    block records the projection plane, the design-space frame (origin + cell
    size + thickness, so a later writeback can place the optimized body), source
    BC links, and warnings. If fewer than one support AND one load can be derived,
    falls back to a preset (warned), so the optimizer still runs.
    """
    package_path = Path(package_path)
    warnings: list[str] = []
    with zipfile.ZipFile(package_path, "r") as zf:
        topo_raw = _read_member_text(zf, "geometry/topology_map.json")
        topology_map = json.loads(topo_raw) if topo_raw else {}
        cae_raw = _read_member_text(zf, "simulation/cae_mapping.json")
        cae_mapping = json.loads(cae_raw) if cae_raw else {}
        setup = _load_cae_setup(zf)

    faces, overall, solid_node = _index_faces(topology_map)
    if not overall:
        raise ValueError("cannot derive design space: no bounding box in geometry/topology_map.json")

    feat_to_faces = _feature_to_faces(cae_mapping)
    setup_bcs = setup.get("boundary_conditions") or []
    setup_loads = setup.get("loads") or []
    if not feat_to_faces and (setup_bcs or setup_loads):
        warnings.append("no simulation/cae_mapping.json — resolving BC/load targets as face ids directly")

    mins, maxs = overall[:3], overall[3:]
    ext = [max(maxs[k] - mins[k], 1e-9) for k in range(3)]
    u, v, w = sorted(range(3), key=lambda k: ext[k], reverse=True)
    axis = ["x", "y", "z"]
    nelx = max(int(resolution), 2)
    nely = max(int(round(resolution * ext[v] / ext[u])), 2)
    du, dv = ext[u] / nelx, ext[v] / nely

    def cell_of_point(p: list[float]) -> tuple[int, int]:
        i = int((p[u] - mins[u]) / ext[u] * nelx)
        j = int((p[v] - mins[v]) / ext[v] * nely)
        return min(max(i, 0), nelx - 1), min(max(j, 0), nely - 1)

    def cells_of_bbox(bb: Any) -> list[list[int]]:
        if not (isinstance(bb, list) and len(bb) >= 6):
            return []
        i0, j0 = cell_of_point([bb[0], bb[1], bb[2]])
        i1, j1 = cell_of_point([bb[3], bb[4], bb[5]])
        i0, i1 = sorted((i0, i1))
        j0, j1 = sorted((j0, j1))
        return [[i, j] for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]

    supports: list[dict[str, Any]] = []
    for bc in setup_bcs:
        fids = _resolve_target_faces(bc.get("target_feature"), feat_to_faces, faces)
        cells = _dedup_cells([c for fid in fids for c in cells_of_bbox(faces.get(fid, {}).get("bbox"))])
        if cells:
            supports.append({"cells": cells, "from": {
                "target_feature": bc.get("target_feature"), "type": bc.get("type"), "face_ids": fids}})
        else:
            warnings.append(f"support '{bc.get('target_feature')}' resolved to no faces/cells — skipped")

    loads: list[dict[str, Any]] = []
    for ld in setup_loads:
        fids = _resolve_target_faces(ld.get("target_feature"), feat_to_faces, faces)
        cells = _dedup_cells([
            list(cell_of_point(faces[fid]["center"])) for fid in fids if faces.get(fid, {}).get("center")
        ])
        direction = ld.get("direction") or [0.0, 0.0, -1.0]
        mag = float(ld.get("value_n") or 1.0)
        fx, fy, fw = mag * float(direction[u]), mag * float(direction[v]), mag * float(direction[w])
        if cells and (fx or fy):
            loads.append({"cells": cells, "fx": fx, "fy": fy, "from": {
                "target_feature": ld.get("target_feature"), "value_n": mag, "direction": direction}})
            if abs(fw) > max(abs(fx), abs(fy)):
                warnings.append(
                    f"load '{ld.get('target_feature')}' is mostly out-of-plane ({axis[w]}); "
                    "the 2D problem keeps only the in-plane component")
        elif abs(fw) > 0:
            warnings.append(
                f"load '{ld.get('target_feature')}' is purely out-of-plane ({axis[w]}); "
                "no in-plane component for the 2D problem — skipped")
        else:
            warnings.append(f"load '{ld.get('target_feature')}' resolved to no force/cells — skipped")

    bcs: dict[str, Any] = {"supports": supports, "loads": loads}
    derived = bool(supports and loads)
    if not derived:
        bcs["preset"] = "cantilever"
        warnings.append(
            "insufficient derived BCs (need ≥1 support and ≥1 load) — falling back to the cantilever preset")

    return {
        "grid": {"nelx": nelx, "nely": nely},
        "volfrac": volfrac, "penalty": penalty, "rmin": rmin, "max_iters": max_iters,
        "objective": objective,
        "bcs": bcs,
        "design_space_node": solid_node,
        "derivation": {
            "source": "cae_setup+topology_map",
            "derived": derived,
            "plane": {"u_axis": axis[u], "v_axis": axis[v], "out_of_plane_axis": axis[w]},
            "design_space_bbox": overall,
            "frame": {
                "origin": [mins[0], mins[1], mins[2]],
                "u_axis": axis[u], "v_axis": axis[v],
                "cell_size": [round(du, 6), round(dv, 6)], "thickness": round(ext[w], 6),
            },
            "support_count": len(supports), "load_count": len(loads),
            "warnings": warnings,
            "limitations": [
                "3D supports/loads are projected onto the plane of the two largest design-space "
                "dimensions; out-of-plane force components are dropped (plane-stress idealization).",
            ],
        },
    }


def run_topology_optimization(problem: dict[str, Any], *, optimizer: str = "simp_2d") -> dict[str, Any]:
    """Run an optimizer and wrap its output in the neutral result contract."""
    requested = str(optimizer or "simp_2d")
    entry = _OPTIMIZER_REGISTRY.get(requested)
    fallback = entry is None
    if entry is None:
        entry = _OPTIMIZER_REGISTRY["simp_2d"]
        requested_name = "simp_2d"
    else:
        requested_name = requested
    opt = entry["fn"](problem)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    threshold = float(problem.get("threshold", 0.5))
    density = opt.get("density") or []
    solid = sum(1 for row in density for v in row if v >= threshold)
    return {
        "format": "aieng.topology_optimization",
        "schema_version": TOPOPT_CONTRACT_VERSION,
        "contract_version": TOPOPT_CONTRACT_VERSION,
        "generated_at_utc": now,
        "optimizer": {
            "name": requested_name,
            "version": entry["version"],
            "method": entry["method"],
            "dimension": entry["dimension"],
            "requested": requested,
            "fallback": fallback,
        },
        "objective": str(problem.get("objective") or "compliance_minimization"),
        "problem": {
            "grid": {"nelx": opt.get("nelx"), "nely": opt.get("nely")},
            "volfrac": opt.get("target_volume_fraction"),
            "penalty": problem.get("penalty", 3.0),
            "rmin": problem.get("rmin", 1.5),
            "bcs_preset": opt.get("bcs_preset"),
            "bcs_source": opt.get("bcs_source", "preset"),
            "design_space_node": problem.get("design_space_node"),
            "derivation": problem.get("derivation"),
        },
        "result": {
            "iterations": opt.get("iterations"),
            "final_compliance": opt.get("final_compliance"),
            "compliance_history": opt.get("compliance_history"),
            "achieved_volume_fraction": opt.get("achieved_volume_fraction"),
            "threshold": threshold,
            "solid_element_count": solid,
            "density_grid": {
                "nrows": opt.get("nely"),
                "ncols": opt.get("nelx"),
                "values": density,
            },
        },
        "provenance": {
            "optimizer_name": requested_name,
            "optimizer_version": entry["version"],
            "design_space_node": problem.get("design_space_node"),
            "contract_version": TOPOPT_CONTRACT_VERSION,
        },
        "limitations": [
            "2D plane-stress, linear-elastic, single isotropic material, regular grid.",
            "Coarse, observational design aid — not a production-grade optimizer.",
        ],
        "warnings": [],
    }


# ── writeback: optimization result → Shape IR representation ─────────────────
# Closes the generative loop. The optimizer emits a density field (analysis-level
# evidence); to make that field a first-class, re-compilable, viewable shape we
# author it back as ONE Shape IR ``density_voxels`` node. The existing compilers
# (build123d / manifold) expand it into extruded voxel geometry, so the optimized
# body flows through the same pipeline as any other Shape IR: compile → mesh/GLB,
# topology, verification, object_registry — and stays linked to its source node.

SHAPE_IR_PATH = "geometry/shape_ir.json"


def extract_density_contours(
    density: list[list[float]], threshold: float, *,
    origin_u: float, origin_v: float, su: float, sv: float, simplify_tol: float = 0.75,
) -> list[list[list[float]]]:
    """Marching-squares contours of a thresholded density field → in-plane polygons.

    Turns the blocky density grid into smooth boundary loops (the material's
    silhouette + internal holes) instead of axis-aligned voxels. Coordinates are
    returned in world (u, v) — each loop is a closed polygon in the design-space
    plane, aligned with the voxel footprint (cell centres). The grid is zero-padded
    so boundary loops close. Returns ``[]`` if scikit-image is unavailable or no
    contour crosses the threshold (the caller can fall back to voxels).
    """
    try:
        from skimage import measure  # optional dependency
    except Exception:
        return []
    arr = np.asarray(density, dtype=float)
    if arr.ndim != 2 or arr.size == 0:
        return []
    padded = np.pad(arr, 1, mode="constant", constant_values=0.0)
    polys: list[list[list[float]]] = []
    for loop in measure.find_contours(padded, level=float(threshold)):
        if simplify_tol > 0:
            loop = measure.approximate_polygon(loop, tolerance=simplify_tol)
        pts: list[list[float]] = []
        for rr, cc in loop:
            i, j = cc - 1, rr - 1  # undo the pad
            pts.append([round(origin_u + (i + 0.5) * su, 6), round(origin_v + (j + 0.5) * sv, 6)])
        if len(pts) >= 4:  # >=3 distinct + closing vertex
            polys.append(pts)
    return polys


def topology_result_to_shape_ir(
    topo_result: dict[str, Any], *,
    representation: str = "manifold_mesh",
    cell_size: tuple[float, float] | None = None,
    thickness: float | None = None,
    origin: tuple[float, float, float] | None = None,
    node_id: str | None = None,
    model_id: str | None = None,
    color: list[float] | None = None,
    use_frame: bool = True,
    method: str = "voxels",
    simplify_tol: float = 0.75,
) -> dict[str, Any]:
    """Author an optimization result into a Shape IR payload (one shape node).

    Pure: maps the neutral topology-optimization result → a Shape IR document.
    ``method`` selects the geometry the body becomes:
    - ``"voxels"`` (default): a ``density_voxels`` node — the thresholded grid as a
      union of extruded voxel boxes (blocky, exact, no extra dependency).
    - ``"contour"``: an ``extruded_region`` node — marching-squares boundary
      polygons of the thresholded field, extruded; a smoother "design suggestion".
      Falls back to voxels (with a note) if no contour can be extracted.
    Either way it is a single labelled node; ``design_space_node`` is carried
    through so the optimized body stays linked to the design space it came from.

    Placement: when the result carries a derivation ``frame`` (origin + in-plane
    axes + cell size + thickness from ``derive_topopt_problem_from_package``) and
    ``use_frame`` is set, the voxels are placed in the design space's own
    coordinate frame — so the optimized body lands exactly where the design space
    is, on the correct plane. Explicit ``cell_size``/``thickness``/``origin`` args
    override the frame; without a frame they default to unit cells at the world
    origin (an abstract grid).
    """
    result = topo_result.get("result") or {}
    grid = result.get("density_grid") or {}
    density = grid.get("values") or topo_result.get("density") or []
    threshold = float(result.get("threshold", topo_result.get("threshold", 0.5)))
    design_space_node = (
        (topo_result.get("provenance") or {}).get("design_space_node")
        or (topo_result.get("problem") or {}).get("design_space_node")
    )
    nid = node_id or (f"optimized_{design_space_node}" if design_space_node else "optimized_topology")

    frame = ((topo_result.get("problem") or {}).get("derivation") or {}).get("frame") or {}
    use_frame = use_frame and bool(frame)
    f_cell = frame.get("cell_size") or [1.0, 1.0]
    u_axis = str(frame.get("u_axis", "x")) if use_frame else "x"
    v_axis = str(frame.get("v_axis", "y")) if use_frame else "y"

    if cell_size is not None:
        sx, sy = float(cell_size[0]), float(cell_size[1])
    elif use_frame:
        sx, sy = float(f_cell[0]), float(f_cell[1] if len(f_cell) > 1 else f_cell[0])
    else:
        sx, sy = 1.0, 1.0

    if thickness is not None:
        sz = float(thickness)
    elif use_frame:
        sz = float(frame.get("thickness", max(sx, sy)))
    else:
        sz = max(sx, sy)

    if origin is not None:
        o = [float(origin[0]), float(origin[1]), float(origin[2])]
    elif use_frame:
        fo = frame.get("origin") or [0.0, 0.0, 0.0]
        o = [float(fo[0]), float(fo[1]), float(fo[2])]
    else:
        o = [0.0, 0.0, 0.0]

    source_optimization = {
        "optimizer": (topo_result.get("optimizer") or {}).get("name"),
        "objective": topo_result.get("objective"),
        "design_space_node": design_space_node,
        "final_compliance": result.get("final_compliance"),
        "achieved_volume_fraction": result.get("achieved_volume_fraction"),
    }

    method = str(method or "voxels").lower()
    polygons: list[list[list[float]]] = []
    if method == "contour":
        ui = _AXIS_INDEX.get(u_axis, 0)
        vi = _AXIS_INDEX.get(v_axis, 1)
        polygons = extract_density_contours(
            density, threshold, origin_u=o[ui], origin_v=o[vi], su=sx, sv=sy, simplify_tol=simplify_tol)
        if not polygons:
            method = "voxels"  # honest fallback when no contour could be extracted
            source_optimization["contour_fallback"] = "no contour extracted (empty field or skimage missing)"

    if method == "contour":
        node: dict[str, Any] = {
            "id": nid, "label": nid, "type": "extruded_region",
            "polygons": polygons, "thickness": sz, "origin": o,
            "u_axis": u_axis, "v_axis": v_axis, "placed_in_frame": use_frame,
            "source_optimization": source_optimization,
        }
    else:
        node = {
            "id": nid, "label": nid, "type": "density_voxels",
            "density": density, "threshold": threshold,
            "cell_size": [sx, sy], "thickness": sz, "origin": o,
            "u_axis": u_axis, "v_axis": v_axis, "placed_in_frame": use_frame,
            "source_optimization": source_optimization,
        }
    if color is not None:
        node["color"] = list(color)

    return {
        "format": "aieng.shape_ir",
        "representation": representation,
        "model_id": model_id or nid,
        "parts": [node],
        "provenance": {
            "from_topology_optimization": True,
            "optimizer": (topo_result.get("optimizer") or {}).get("name"),
            "design_space_node": design_space_node,
            "topopt_contract_version": topo_result.get("contract_version"),
        },
    }


def write_shape_ir_from_topology_optimization(
    package_path: str | Path, *,
    representation: str = "manifold_mesh",
    cell_size: tuple[float, float] | None = None,
    thickness: float | None = None,
    origin: tuple[float, float, float] | None = None,
    node_id: str | None = None,
    color: list[float] | None = None,
    use_frame: bool = True,
    method: str = "voxels",
    simplify_tol: float = 0.75,
) -> dict[str, Any]:
    """Read a package's topology-optimization result and (re)write geometry/shape_ir.json.

    Reads ``analysis/topology_optimization.json``, authors the Shape IR document,
    and writes it as ``geometry/shape_ir.json`` (replacing any existing member).
    ``method`` chooses ``"voxels"`` (blocky union) or ``"contour"`` (smooth
    marching-squares boundary, extruded). By default (``use_frame``) the optimized
    body is placed in the design space's own coordinate frame when the result
    carries a derivation frame. Does NOT compile — the caller (workbench) recompiles
    via the representation's runtime to produce mesh/GLB + topology + verification +
    registry. Returns the Shape IR payload.
    """
    package_path = Path(package_path)
    with zipfile.ZipFile(package_path, "r") as zf:
        if TOPOLOGY_OPTIMIZATION_PATH not in zf.namelist():
            raise FileNotFoundError(
                f"{TOPOLOGY_OPTIMIZATION_PATH} not in package — run topology optimization first"
            )
        topo_result = json.loads(zf.read(TOPOLOGY_OPTIMIZATION_PATH))

    payload = topology_result_to_shape_ir(
        topo_result, representation=representation, cell_size=cell_size,
        thickness=thickness, origin=origin, node_id=node_id, color=color, use_frame=use_frame,
        method=method, simplify_tol=simplify_tol,
    )
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != SHAPE_IR_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(SHAPE_IR_PATH, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return payload


def write_topology_optimization(
    package_path: str | Path, problem: dict[str, Any], *, optimizer: str = "simp_2d",
) -> dict[str, Any]:
    """Run optimization and write analysis/topology_optimization.json into a package."""
    result = run_topology_optimization(problem, optimizer=optimizer)
    package_path = Path(package_path)
    if not package_path.exists():
        return result
    data = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != TOPOLOGY_OPTIMIZATION_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(TOPOLOGY_OPTIMIZATION_PATH, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return result
