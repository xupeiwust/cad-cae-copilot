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

Honest scope of the built-in optimizer: 2D, plane-stress, linear-elastic, single
isotropic material, regular grid, coarse. It is an observational design aid, not a
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
    preset = str((problem.get("bcs") or {}).get("preset", "cantilever"))

    KE = _element_stiffness()
    ndof = 2 * (nelx + 1) * (nely + 1)
    fixed, F = _boundary_conditions(nelx, nely, preset)
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
            "design_space_node": problem.get("design_space_node"),
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


def topology_result_to_shape_ir(
    topo_result: dict[str, Any], *,
    representation: str = "manifold_mesh",
    cell_size: tuple[float, float] = (1.0, 1.0),
    thickness: float | None = None,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    node_id: str | None = None,
    model_id: str | None = None,
    color: list[float] | None = None,
) -> dict[str, Any]:
    """Author an optimization result into a Shape IR payload (one density_voxels node).

    Pure: maps the neutral topology-optimization result → a Shape IR document. The
    density grid + threshold become a single ``density_voxels`` node that the
    registered compilers expand into extruded voxel geometry. ``design_space_node``
    is carried through so the optimized body stays linked to the design space it
    came from.
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
    sx, sy = float(cell_size[0]), float(cell_size[1])
    sz = float(thickness) if thickness is not None else max(sx, sy)

    node: dict[str, Any] = {
        "id": nid,
        "label": nid,
        "type": "density_voxels",
        "density": density,
        "threshold": threshold,
        "cell_size": [sx, sy],
        "thickness": sz,
        "origin": [float(origin[0]), float(origin[1]), float(origin[2])],
        "source_optimization": {
            "optimizer": (topo_result.get("optimizer") or {}).get("name"),
            "objective": topo_result.get("objective"),
            "design_space_node": design_space_node,
            "final_compliance": result.get("final_compliance"),
            "achieved_volume_fraction": result.get("achieved_volume_fraction"),
        },
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
    cell_size: tuple[float, float] = (1.0, 1.0),
    thickness: float | None = None,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    node_id: str | None = None,
    color: list[float] | None = None,
) -> dict[str, Any]:
    """Read a package's topology-optimization result and (re)write geometry/shape_ir.json.

    Reads ``analysis/topology_optimization.json``, authors the Shape IR document,
    and writes it as ``geometry/shape_ir.json`` (replacing any existing member).
    Does NOT compile — the caller (workbench) recompiles via the representation's
    runtime to produce mesh/GLB + topology + verification + registry. Returns the
    Shape IR payload.
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
        thickness=thickness, origin=origin, node_id=node_id, color=color,
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
