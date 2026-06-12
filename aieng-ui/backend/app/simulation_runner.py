"""Simulation trigger: Gmsh mesh + CalculiX solve from AI preprocessing output.

Reads simulation/setup.yaml and simulation/cae_mapping.json from the .aieng package,
meshes the STEP geometry with Gmsh, generates a CalculiX input deck, runs the solver,
parses FRD results, and writes everything back atomically.

Graceful degradation: if Gmsh or CalculiX are not installed, returns
{"status": "tools_unavailable", "missing_tools": [...]} without raising.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import yaml

from .config import ensure_aieng_on_path
from .project_io import validate_cae_topology_references
from fastapi import HTTPException


# ── Tool availability ─────────────────────────────────────────────────────────

def _find_ccx() -> str | None:
    for candidate in ("ccx", "ccx_linux", "ccx2.21", "ccx_static"):
        cmd = shutil.which(candidate)
        if cmd:
            return cmd
    return None


def _gmsh_available() -> bool:
    try:
        import gmsh  # noqa: F401
        return True
    except ImportError:
        return False


def check_simulation_tools() -> dict[str, Any]:
    """Return availability status of Gmsh and CalculiX."""
    ccx = _find_ccx()
    gmsh_ok = _gmsh_available()
    missing = [t for t, ok in [("gmsh", gmsh_ok), ("ccx", ccx is not None)] if not ok]
    return {
        "gmsh": gmsh_ok,
        "calculix": ccx is not None,
        "calculix_cmd": ccx,
        "ready": len(missing) == 0,
        "missing": missing,
    }


# ── Package I/O helpers ───────────────────────────────────────────────────────

def _read_member(package_path: Path, member: str) -> bytes | None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if member in zf.namelist():
                return zf.read(member)
    except Exception:
        pass
    return None


def _extract_step(package_path: Path, work_dir: Path) -> Path | None:
    """Extract the geometry STEP file to work_dir. Returns path or None."""
    for candidate in ("geometry/generated.step", "geometry/model.step", "geometry/part.step"):
        raw = _read_member(package_path, candidate)
        if raw:
            out = work_dir / "model.step"
            out.write_bytes(raw)
            return out
    return None


def _write_results_to_package(
    package_path: Path,
    solver_log: str,
    frd_bytes: bytes | None,
    summary: dict[str, Any],
    mesh_inp_bytes: bytes | None = None,
) -> None:
    """Atomically write solver_log, optional FRD/mesh, and results_summary into the package."""
    files: dict[str, bytes] = {
        "simulation/solver_log.txt": solver_log.encode(),
        "simulation/results_summary.json": json.dumps(summary, indent=2, ensure_ascii=False).encode(),
    }
    if frd_bytes:
        files["simulation/result.frd"] = frd_bytes
    if mesh_inp_bytes:
        files["simulation/mesh.inp"] = mesh_inp_bytes

    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with zipfile.ZipFile(package_path, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename not in files:
                    dst.writestr(item, src.read(item.filename))
            for archive_path, content_bytes in files.items():
                dst.writestr(archive_path, content_bytes)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── Gmsh meshing ──────────────────────────────────────────────────────────────

def _mesh_with_gmsh(step_path: Path, work_dir: Path, mesh_size_mm: float) -> Path:
    """Mesh the STEP file with Gmsh and export a CalculiX-format .inp mesh."""
    import gmsh

    out_inp = work_dir / "mesh.inp"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("model")
        gmsh.merge(str(step_path))
        gmsh.model.occ.synchronize()

        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_size_mm)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_size_mm / 4.0)
        gmsh.option.setNumber("Mesh.Algorithm3D", 4)  # Frontal-Delaunay

        volumes = gmsh.model.getEntities(3)
        if not volumes:
            raise RuntimeError("No 3D volumes found in STEP — cannot mesh")
        gmsh.model.addPhysicalGroup(3, [v[1] for v in volumes], tag=1, name="EALL")

        # Surface physical groups needed for NSET construction later
        surfaces = gmsh.model.getEntities(2)
        for surf_dim, surf_tag in surfaces:
            gmsh.model.addPhysicalGroup(2, [surf_tag], tag=1000 + surf_tag, name=f"SURF{surf_tag}")

        gmsh.model.mesh.generate(3)
        gmsh.write(str(out_inp))
    finally:
        gmsh.finalize()

    return out_inp


# ── Node parsing ──────────────────────────────────────────────────────────────

def _parse_inp_nodes(inp_path: Path) -> dict[int, tuple[float, float, float]]:
    """Parse node coordinates from a Gmsh-generated CalculiX .inp file."""
    nodes: dict[int, tuple[float, float, float]] = {}
    in_node_section = False
    for line in inp_path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("*NODE"):
            in_node_section = True
            continue
        if stripped.startswith("*"):
            in_node_section = False
        if in_node_section and stripped and not stripped.startswith("**"):
            parts = [p.strip() for p in stripped.split(",")]
            if len(parts) >= 4:
                try:
                    nid = int(parts[0])
                    nodes[nid] = (float(parts[1]), float(parts[2]), float(parts[3]))
                except ValueError:
                    pass
    return nodes


# ── Face → node mapping ───────────────────────────────────────────────────────

def _nodes_on_face(
    nodes: dict[int, tuple[float, float, float]],
    face_entity: dict[str, Any],
) -> list[int]:
    """Find node IDs that lie on a topology face.

    Strategy (in priority order):
    1. Cylinder: radial distance from inferred axis + Z-extent check.
    2. Plane with stored normal: point-to-plane distance using face normal and
       centroid as the plane origin, plus coarse AABB filter.
       Works for axis-aligned AND inclined/chamfered planes.
    3. Fallback (no normal stored): thin-dimension bounding-box heuristic
       (axis-aligned planes only — retained for backwards compatibility).
    """
    bbox = face_entity.get("bounding_box", [])
    if len(bbox) < 6:
        return []

    surface_type = face_entity.get("surface_type", "plane")
    # Tolerance: 2% of longest bbox dimension, minimum 0.5 mm.
    span = max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2], 1.0)
    tol = max(0.5, span * 0.02)
    # Free-form faces (loft/sweep/sphere) only carry a PROXY normal sampled at the
    # UV midpoint, so the tangent-plane band must be wider to capture a usable
    # patch of the curved surface near the pick. Approximate by design.
    is_freeform = bool(face_entity.get("freeform")) or (
        surface_type == "other" and face_entity.get("normal")
    )
    if is_freeform:
        tol = max(1.0, span * 0.10)

    # ── Cylinder ──────────────────────────────────────────────────────────────
    if surface_type == "cylinder":
        radius = float(face_entity.get("radius", 0.0))
        cx = (bbox[0] + bbox[3]) / 2.0
        cy = (bbox[1] + bbox[4]) / 2.0
        zmin, zmax = bbox[2], bbox[5]
        result = []
        for nid, (x, y, z) in nodes.items():
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if abs(dist - radius) < tol and zmin - tol <= z <= zmax + tol:
                result.append(nid)
        return result

    # ── Planar face — normal-vector path ──────────────────────────────────────
    raw_normal = face_entity.get("normal")
    if raw_normal and len(raw_normal) == 3:
        nx, ny, nz = float(raw_normal[0]), float(raw_normal[1]), float(raw_normal[2])
        mag = (nx * nx + ny * ny + nz * nz) ** 0.5
        if mag > 1e-9:
            nx, ny, nz = nx / mag, ny / mag, nz / mag
            # Use stored centroid; fall back to bbox midpoint
            cpt = face_entity.get("center") or [
                (bbox[0] + bbox[3]) / 2.0,
                (bbox[1] + bbox[4]) / 2.0,
                (bbox[2] + bbox[5]) / 2.0,
            ]
            px, py, pz = float(cpt[0]), float(cpt[1]), float(cpt[2])
            # Plane equation: dot(n, point) = d
            d = nx * px + ny * py + nz * pz
            result = []
            for nid, (x, y, z) in nodes.items():
                # Coarse AABB filter — rejects nodes far from face region
                if not (
                    bbox[0] - tol <= x <= bbox[3] + tol
                    and bbox[1] - tol <= y <= bbox[4] + tol
                    and bbox[2] - tol <= z <= bbox[5] + tol
                ):
                    continue
                # Exact point-to-plane distance
                if abs(nx * x + ny * y + nz * z - d) <= tol:
                    result.append(nid)
            return result

    # ── Fallback: thin-dimension bounding-box heuristic (axis-aligned only) ──
    dims = [bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]]
    thin = dims.index(min(dims))
    center = (bbox[thin] + bbox[thin + 3]) / 2.0
    result = []
    for nid, (x, y, z) in nodes.items():
        coords = (x, y, z)
        if abs(coords[thin] - center) > tol:
            continue
        in_plane = all(
            bbox[i] - tol <= coords[i] <= bbox[i + 3] + tol
            for i in range(3)
            if i != thin
        )
        if in_plane:
            result.append(nid)
    return result


def _build_nsets(
    nodes: dict[int, tuple[float, float, float]],
    topology: dict[str, Any],
    cae_mapping: dict[str, Any],
) -> dict[str, list[int]]:
    """Map cae_mapping face IDs to mesh node IDs via topology bounding boxes."""
    face_index: dict[str, dict[str, Any]] = {
        e["id"]: e
        for e in (topology.get("entities") or topology.get("faces") or [])
        if isinstance(e, dict) and e.get("type") == "face" and "id" in e
    }

    nsets: dict[str, list[int]] = {}
    for mapping in cae_mapping.get("mappings") or []:
        nset_name = mapping.get("cae_entity", "")
        if not nset_name:
            continue
        node_ids: set[int] = set()
        for fid in mapping.get("face_ids") or []:
            entity = face_index.get(fid)
            if entity:
                node_ids.update(_nodes_on_face(nodes, entity))
        nsets[nset_name] = sorted(node_ids)

    return nsets


def _unresolved_bc_load_faces(
    setup: dict[str, Any],
    cae_mapping: dict[str, Any],
    nsets: dict[str, list[int]],
) -> list[dict[str, Any]]:
    """Return loads/BCs whose mapped face(s) matched zero mesh nodes.

    A load or boundary condition whose target feature maps to an NSET that
    resolved to no nodes (face ↔ mesh mismatch) is silently dropped by the deck
    builder, so the solve would run with a missing constraint/load and produce a
    wrong (often singular) result. Surfacing these as @face hints lets the caller
    re-pick the face — or remesh — *before* paying for the solver run. Targets
    with no mapping at all are left to the normal completeness checks; this only
    flags the "selected a face but it caught no nodes" case.
    """
    feat_map: dict[str, tuple[str, list[str]]] = {}
    for m in cae_mapping.get("mappings") or []:
        fid = (m.get("maps_to") or {}).get("feature_id")
        if fid:
            feat_map[fid] = (m.get("cae_entity", ""), list(m.get("face_ids") or []))

    problems: list[dict[str, Any]] = []
    for kind, items in (
        ("boundary_condition", setup.get("boundary_conditions") or []),
        ("load", setup.get("loads") or []),
    ):
        for item in items:
            target = item.get("target_feature", "")
            nset_name, face_ids = feat_map.get(target, ("", []))
            if nset_name and not nsets.get(nset_name):
                problems.append({
                    "kind": kind,
                    "target_feature": target,
                    "cae_entity": nset_name,
                    "face_pointers": [f"@face:{fid}" for fid in face_ids],
                })
    return problems


# ── CalculiX deck generation ──────────────────────────────────────────────────

def _sanitize_name(name: str) -> str:
    """Make a name safe for CalculiX (alphanumeric + underscore, max 80 chars)."""
    import re
    return re.sub(r"[^A-Za-z0-9_]", "_", name)[:80]


def _build_calculix_deck(
    mesh_inp_text: str,
    setup: dict[str, Any],
    nsets: dict[str, list[int]],
    cae_mapping: dict[str, Any],
) -> str:
    """Build the full CalculiX input deck from the Gmsh mesh + AI preprocessing output."""
    lines: list[str] = []

    # ── Keep mesh sections from Gmsh verbatim (nodes + elements + elsets) ──
    # Stop if Gmsh somehow wrote material/BC/step sections (shouldn't happen).
    for line in mesh_inp_text.splitlines():
        up = line.strip().upper()
        if up.startswith("*MATERIAL") or up.startswith("*BOUNDARY") or up.startswith("*STEP"):
            break
        lines.append(line)

    # ── NALL / NSET definitions ──────────────────────────────────────────────
    if nsets:
        for nset_name, node_ids in nsets.items():
            if not node_ids:
                continue
            safe = _sanitize_name(nset_name)
            lines.append(f"*NSET, NSET={safe}")
            for i in range(0, len(node_ids), 16):
                lines.append(", ".join(str(n) for n in node_ids[i : i + 16]))

    # ── Material ─────────────────────────────────────────────────────────────
    mat_name = setup.get("material_name", "Al6061_T6")
    mat_safe = _sanitize_name(mat_name)
    mat_props = (setup.get("materials") or {}).get(mat_name) or {}
    E = float(mat_props.get("youngs_modulus_mpa", 69000))
    nu = float(mat_props.get("poisson_ratio", 0.33))
    # Convert kg/m³ → t/mm³ for consistent mm/N/MPa unit system
    rho_kg_m3 = float(mat_props.get("density_kg_m3", 2700))
    rho_t_mm3 = rho_kg_m3 * 1e-12

    lines += [
        f"*MATERIAL, NAME={mat_safe}",
        "*ELASTIC",
        f"{E:.1f}, {nu}",
        "*DENSITY",
        f"{rho_t_mm3:.6e}",
        f"*SOLID SECTION, ELSET=EALL, MATERIAL={mat_safe}",
        "",
    ]

    # ── STEP ─────────────────────────────────────────────────────────────────
    lines += ["*STEP", "*STATIC"]

    # Build feature_id → cae_entity index
    feat_to_nset: dict[str, str] = {}
    for m in cae_mapping.get("mappings") or []:
        fid = (m.get("maps_to") or {}).get("feature_id")
        if fid:
            feat_to_nset[fid] = m.get("cae_entity", "")

    # ── Boundary conditions ──────────────────────────────────────────────────
    bc_written = 0
    for bc in setup.get("boundary_conditions") or []:
        target = bc.get("target_feature", "")
        nset_name = feat_to_nset.get(target, "")
        safe = _sanitize_name(nset_name)
        if safe and nsets.get(nset_name):
            bc_type = bc.get("type", "fixed")
            if bc_type == "fixed":
                lines.append("*BOUNDARY")
                lines.append(f"{safe}, 1, 6")  # fix all 6 DOFs
                bc_written += 1

    # ── Loads ────────────────────────────────────────────────────────────────
    load_written = 0
    for ld in setup.get("loads") or []:
        target = ld.get("target_feature", "")
        nset_name = feat_to_nset.get(target, "")
        safe = _sanitize_name(nset_name)
        node_ids = nsets.get(nset_name) or []
        if safe and node_ids:
            value_n = float(ld.get("value_n") or 0.0)
            direction = ld.get("direction") or [0.0, 0.0, -1.0]
            n_nodes = len(node_ids)
            force_per_node = value_n / n_nodes if n_nodes else 0.0
            for dof, comp in enumerate(direction[:3], start=1):
                if abs(comp) > 1e-9:
                    lines.append("*CLOAD")
                    lines.append(f"{safe}, {dof}, {force_per_node * comp:.6f}")
            load_written += 1

    # ── Output requests ──────────────────────────────────────────────────────
    lines += [
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ]

    return "\n".join(lines) + "\n", bc_written, load_written


# ── CalculiX execution ────────────────────────────────────────────────────────

def _run_calculix(
    inp_path: Path,
    work_dir: Path,
    timeout: int = 180,
) -> tuple[int, str, Path | None]:
    """Run CalculiX. Returns (returncode, combined_log, frd_path or None)."""
    ccx_cmd = _find_ccx()
    if not ccx_cmd:
        raise RuntimeError("CalculiX (ccx) not found")

    result = subprocess.run(
        [ccx_cmd, inp_path.stem],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    log = result.stdout + "\n" + result.stderr
    frd = work_dir / f"{inp_path.stem}.frd"
    return result.returncode, log, frd if frd.exists() else None


# ── Solver failure diagnosis ──────────────────────────────────────────────────

def _diagnose_solver_log(log: str) -> list[str]:
    """Scan a CalculiX log for common failure patterns and return actionable messages."""
    diagnoses: list[str] = []
    up = log.upper()

    if "SINGULAR" in up or "ZERO PIVOT" in up or "ZERO DIAGONAL" in up:
        diagnoses.append(
            "Stiffness matrix is singular — the model may be under-constrained. "
            "Verify that all rigid-body modes are suppressed by the boundary conditions."
        )
    if "TOO MANY INCREMENTS" in up:
        diagnoses.append(
            "Solver did not converge within the increment limit — "
            "try a finer mesh or reduce the applied load magnitude."
        )
    if "DIVERGENCE" in up:
        diagnoses.append(
            "Solution diverged — check for unrealistically large loads or verify material properties."
        )
    if "NO ELEMENTS" in up or "EMPTY ELEMENT SET" in up:
        diagnoses.append(
            "An element set is empty — the face-to-node mapping may have failed. "
            "Check that the geometry STEP and topology_map.json are consistent."
        )
    if "ERROR IN FACE" in up or "INCONSISTENT ORIENTATION" in up:
        diagnoses.append(
            "Mesh has inconsistently oriented faces — the STEP geometry may have "
            "surface normal issues. Try regenerating the CAD model."
        )
    if not diagnoses:
        # Extract the first *ERROR line from the log as a fallback
        for line in log.splitlines():
            if "*ERROR" in line.upper() or "ERROR:" in line.upper():
                diagnoses.append(f"Solver reported: {line.strip()}")
                break
        if not diagnoses:
            diagnoses.append(
                "Solver exited with a non-zero return code — "
                "see simulation/solver_log.txt for the full output."
            )
    return diagnoses


# ── Result extraction ─────────────────────────────────────────────────────────

def _extract_metrics(frd_path: Path) -> dict[str, Any]:
    """Parse FRD file using the existing aieng simulation module."""
    ensure_aieng_on_path()
    from aieng.simulation.frd_result_extractor import extract_computed_metrics

    return extract_computed_metrics(frd_path)


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_simulation(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Mesh with Gmsh + solve with CalculiX + parse results, all in one call.

    Requires confirmed=true in payload (approval gate — this runs external processes).
    Writes simulation/solver_log.txt, simulation/result.frd, and
    simulation/results_summary.json into the .aieng package atomically.
    """
    from .project_io import get_project, resolve_project_path

    if not payload.get("confirmed"):
        raise HTTPException(
            status_code=400,
            detail="confirmed=true is required — simulation runs external processes (Gmsh + CalculiX)",
        )

    project = get_project(settings, project_id)
    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        raise HTTPException(status_code=404, detail=".aieng package not found")

    # ── Tool check (graceful degradation) ────────────────────────────────────
    tools = check_simulation_tools()
    if not tools["ready"]:
        return {
            "status": "tools_unavailable",
            "project_id": project_id,
            "missing_tools": tools["missing"],
            "message": f"Required tools not installed: {', '.join(tools['missing'])}. "
                       "Install Gmsh (pip install gmsh) and CalculiX (ccx).",
        }

    # ── Prerequisites ─────────────────────────────────────────────────────────
    setup_raw = _read_member(package_path, "simulation/setup.yaml")
    if not setup_raw:
        raise HTTPException(
            status_code=422,
            detail="simulation/setup.yaml not found — run AI preprocessing first",
        )
    setup = yaml.safe_load(setup_raw)

    cae_raw = _read_member(package_path, "simulation/cae_mapping.json")
    cae_mapping: dict[str, Any] = json.loads(cae_raw) if cae_raw else {"mappings": []}

    topo_raw = _read_member(package_path, "geometry/topology_map.json")
    topology: dict[str, Any] = json.loads(topo_raw) if topo_raw else {}

    # Fail fast if the CAE face references are stale relative to current topology.
    topology_validation = validate_cae_topology_references(package_path)
    if not topology_validation["valid"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "stale_topology_references",
                "message": (
                    "Aborted before meshing: CAE face references do not match the "
                    "current topology. Re-run AI preprocessing to refresh face "
                    "references, or update simulation/cae_mapping.json manually."
                ),
                "topology_validation": topology_validation,
            },
        )

    mesh_size_mm = float(
        payload.get("mesh_size_mm")
        or (setup.get("mesh") or {}).get("target_size_mm")
        or 2.5
    )
    timeout = int(payload.get("timeout_s") or 180)

    with tempfile.TemporaryDirectory(prefix="aieng_sim_") as tmp_str:
        work_dir = Path(tmp_str)

        # ── Extract STEP ──────────────────────────────────────────────────────
        step_path = _extract_step(package_path, work_dir)
        if not step_path:
            raise HTTPException(
                status_code=422,
                detail="No STEP file in package — run text-to-CAD generation first",
            )

        # ── Gmsh mesh ─────────────────────────────────────────────────────────
        mesh_inp = _mesh_with_gmsh(step_path, work_dir, mesh_size_mm)
        nodes = _parse_inp_nodes(mesh_inp)
        node_count = len(nodes)

        # ── Build NSETs from topology + cae_mapping ───────────────────────────
        nsets = _build_nsets(nodes, topology, cae_mapping)
        empty_nsets = [k for k, v in nsets.items() if not v]

        # Fail fast: a load/BC whose face matched zero mesh nodes would be
        # silently dropped, yielding a wrong/singular solve. Abort with @face
        # hints before invoking CalculiX so the caller can re-pick or remesh.
        unresolved = _unresolved_bc_load_faces(setup, cae_mapping, nsets)
        if unresolved:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unresolved_face_mapping",
                    "message": (
                        "Aborted before solving: load/boundary-condition face(s) "
                        "matched zero mesh nodes. Re-pick the face(s) or reduce "
                        "mesh_size_mm, then retry."
                    ),
                    "unresolved": unresolved,
                },
            )

        # ── Generate solver deck ──────────────────────────────────────────────
        mesh_text = mesh_inp.read_text(errors="replace")
        deck_text, bc_count, load_count = _build_calculix_deck(
            mesh_text, setup, nsets, cae_mapping
        )
        deck_inp = work_dir / "aieng_run.inp"
        deck_inp.write_text(deck_text)

        # ── Run CalculiX ──────────────────────────────────────────────────────
        returncode, solver_log, frd_path = _run_calculix(deck_inp, work_dir, timeout=timeout)

        # ── Parse results ─────────────────────────────────────────────────────
        warnings: list[str] = []
        if empty_nsets:
            warnings.append(f"NSETs with no matched nodes (face ID mismatch): {empty_nsets}")
        if bc_count == 0:
            warnings.append("No boundary conditions were applied — model may be unconstrained")
        if load_count == 0:
            warnings.append("No loads were applied")

        von_mises_max: float | None = None
        displacement_max: float | None = None
        frd_bytes: bytes | None = None
        full_metrics: dict[str, Any] = {}

        if frd_path:
            frd_bytes = frd_path.read_bytes()
            try:
                extracted = _extract_metrics(frd_path)
                load_cases = extracted.get("load_cases") or {}
                lc = next(iter(load_cases.values()), {}) if load_cases else {}
                von_mises_max = lc.get("max_von_mises_stress_mpa")
                displacement_max = lc.get("max_displacement_mm")
                warnings.extend(extracted.get("warnings") or [])
                full_metrics = extracted
            except Exception as exc:
                warnings.append(f"FRD result parsing failed: {exc}")

        status = "success" if returncode == 0 and frd_path else "solver_error"

        # ── Post-processing: verdict vs design targets ────────────────────────
        verdict: dict[str, Any] = {}
        if status == "success" and (von_mises_max is not None or displacement_max is not None):
            from . import post_processing

            targets_raw = _read_member(package_path, "task/design_targets.yaml")
            design_targets: list[dict[str, Any]] = []
            if targets_raw:
                try:
                    import yaml as _yaml
                    doc = _yaml.safe_load(targets_raw)
                    if isinstance(doc, dict):
                        design_targets = doc.get("targets") or []
                except Exception:
                    pass
            material_name = (setup.get("material_name") or setup.get("material") or "")
            verdict = post_processing.interpret_results(
                von_mises_max, displacement_max, design_targets, str(material_name)
            )

        results_summary: dict[str, Any] = {
            "schema_version": "0.1",
            "solver": "CalculiX",
            "status": status,
            "returncode": returncode,
            "node_count": node_count,
            "mesh_size_mm": mesh_size_mm,
            "bc_count": bc_count,
            "load_count": load_count,
            "von_mises_max_mpa": von_mises_max,
            "displacement_max_mm": displacement_max,
            "warnings": warnings,
            "full_metrics": full_metrics,
            "verdict": verdict,
        }

        # ── Write artifacts atomically ────────────────────────────────────────
        mesh_inp_bytes = mesh_inp.read_bytes()
        written = ["simulation/solver_log.txt", "simulation/results_summary.json", "simulation/mesh.inp"]
        if frd_bytes:
            written.append("simulation/result.frd")
        _write_results_to_package(package_path, solver_log, frd_bytes, results_summary, mesh_inp_bytes)

        response: dict[str, Any] = {
            "status": status,
            "project_id": project_id,
            "returncode": returncode,
            "von_mises_max_mpa": von_mises_max,
            "displacement_max_mm": displacement_max,
            "node_count": node_count,
            "mesh_size_mm": mesh_size_mm,
            "written_artifacts": written,
            "warnings": warnings,
            "verdict": verdict,
        }
        if returncode != 0:
            response["solver_log_tail"] = solver_log[-2000:]
            response["diagnosis"] = _diagnose_solver_log(solver_log)
        return response


def _sse(event: dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def run_simulation_stream(
    settings: Any,
    project_id: str,
    payload: dict[str, Any],
) -> Generator[str, None, None]:
    """Streaming variant of run_simulation — yields SSE-formatted progress events.

    Events: checking_tools → meshing → building_nsets → solving → parsing →
            done (with full result) | error (on unexpected failure).

    The generator never raises; all failures are surfaced as SSE error events.
    """
    from .project_io import get_project, resolve_project_path

    if not payload.get("confirmed"):
        yield _sse({"step": "error", "message": "confirmed=true is required"})
        return

    try:
        project = get_project(settings, project_id)
    except Exception as exc:
        yield _sse({"step": "error", "message": f"Project not found: {exc}"})
        return

    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        yield _sse({"step": "error", "message": ".aieng package not found"})
        return

    # ── Step 1: check tools ───────────────────────────────────────────────────
    yield _sse({"step": "checking_tools", "message": "Checking Gmsh and CalculiX…"})
    tools = check_simulation_tools()
    if not tools["ready"]:
        result: dict[str, Any] = {
            "status": "tools_unavailable",
            "project_id": project_id,
            "missing_tools": tools["missing"],
            "message": f"Required tools not installed: {', '.join(tools['missing'])}.",
        }
        yield _sse({"step": "done", "message": "Tools unavailable", "result": result})
        return

    # ── Load prerequisites ────────────────────────────────────────────────────
    setup_raw = _read_member(package_path, "simulation/setup.yaml")
    if not setup_raw:
        yield _sse({"step": "error", "message": "simulation/setup.yaml not found — run AI preprocessing first"})
        return
    setup = yaml.safe_load(setup_raw)

    cae_raw = _read_member(package_path, "simulation/cae_mapping.json")
    cae_mapping: dict[str, Any] = json.loads(cae_raw) if cae_raw else {"mappings": []}

    topo_raw = _read_member(package_path, "geometry/topology_map.json")
    topology: dict[str, Any] = json.loads(topo_raw) if topo_raw else {}

    mesh_size_mm = float(
        payload.get("mesh_size_mm")
        or (setup.get("mesh") or {}).get("target_size_mm")
        or 2.5
    )
    timeout = int(payload.get("timeout_s") or 180)

    try:
        with tempfile.TemporaryDirectory(prefix="aieng_sim_") as tmp_str:
            work_dir = Path(tmp_str)

            # ── Step 2: extract STEP ──────────────────────────────────────────
            step_path = _extract_step(package_path, work_dir)
            if not step_path:
                yield _sse({"step": "error", "message": "No STEP file in package — run text-to-CAD generation first"})
                return

            # ── Step 3: mesh ──────────────────────────────────────────────────
            yield _sse({"step": "meshing", "message": f"Generating mesh with Gmsh (target size {mesh_size_mm} mm)…"})
            mesh_inp = _mesh_with_gmsh(step_path, work_dir, mesh_size_mm)
            nodes = _parse_inp_nodes(mesh_inp)
            node_count = len(nodes)

            # ── Step 4: build NSETs ───────────────────────────────────────────
            face_count = len(cae_mapping.get("mappings") or [])
            yield _sse({"step": "building_nsets", "message": f"Mapping {face_count} face(s) to mesh nodes ({node_count:,} nodes)…"})
            nsets = _build_nsets(nodes, topology, cae_mapping)
            empty_nsets = [k for k, v in nsets.items() if not v]

            # Fail fast before solving if a load/BC face matched zero mesh nodes
            # (it would be silently dropped → wrong/singular solve).
            unresolved = _unresolved_bc_load_faces(setup, cae_mapping, nsets)
            if unresolved:
                hint_faces = ", ".join(
                    fp for prob in unresolved for fp in prob["face_pointers"]
                ) or "(no face hints available)"
                yield _sse({
                    "step": "error",
                    "code": "unresolved_face_mapping",
                    "message": (
                        "Load/BC face(s) matched zero mesh nodes — aborted before "
                        f"solving. Re-pick or remesh: {hint_faces}"
                    ),
                    "unresolved": unresolved,
                })
                return

            mesh_text = mesh_inp.read_text(errors="replace")
            deck_text, bc_count, load_count = _build_calculix_deck(mesh_text, setup, nsets, cae_mapping)
            deck_inp = work_dir / "aieng_run.inp"
            deck_inp.write_text(deck_text)

            # ── Step 5: solve ─────────────────────────────────────────────────
            yield _sse({"step": "solving", "message": f"Running CalculiX ({node_count:,} nodes)…"})
            returncode, solver_log, frd_path = _run_calculix(deck_inp, work_dir, timeout=timeout)

            # ── Step 6: parse results ─────────────────────────────────────────
            yield _sse({"step": "parsing", "message": "Parsing FRD results…"})
            warnings: list[str] = []
            if empty_nsets:
                warnings.append(f"NSETs with no matched nodes (face ID mismatch): {empty_nsets}")
            if bc_count == 0:
                warnings.append("No boundary conditions were applied — model may be unconstrained")
            if load_count == 0:
                warnings.append("No loads were applied")

            von_mises_max: float | None = None
            displacement_max: float | None = None
            frd_bytes: bytes | None = None
            full_metrics: dict[str, Any] = {}

            if frd_path:
                frd_bytes = frd_path.read_bytes()
                try:
                    extracted = _extract_metrics(frd_path)
                    load_cases = extracted.get("load_cases") or {}
                    lc = next(iter(load_cases.values()), {}) if load_cases else {}
                    von_mises_max = lc.get("max_von_mises_stress_mpa")
                    displacement_max = lc.get("max_displacement_mm")
                    warnings.extend(extracted.get("warnings") or [])
                    full_metrics = extracted
                except Exception as exc:
                    warnings.append(f"FRD result parsing failed: {exc}")

            status = "success" if returncode == 0 and frd_path else "solver_error"

            verdict: dict[str, Any] = {}
            if status == "success" and (von_mises_max is not None or displacement_max is not None):
                from . import post_processing

                targets_raw = _read_member(package_path, "task/design_targets.yaml")
                design_targets: list[dict[str, Any]] = []
                if targets_raw:
                    try:
                        import yaml as _yaml
                        doc = _yaml.safe_load(targets_raw)
                        if isinstance(doc, dict):
                            design_targets = doc.get("targets") or []
                    except Exception:
                        pass
                material_name = (setup.get("material_name") or setup.get("material") or "")
                verdict = post_processing.interpret_results(
                    von_mises_max, displacement_max, design_targets, str(material_name)
                )

            results_summary: dict[str, Any] = {
                "schema_version": "0.1",
                "solver": "CalculiX",
                "status": status,
                "returncode": returncode,
                "node_count": node_count,
                "mesh_size_mm": mesh_size_mm,
                "bc_count": bc_count,
                "load_count": load_count,
                "von_mises_max_mpa": von_mises_max,
                "displacement_max_mm": displacement_max,
                "warnings": warnings,
                "full_metrics": full_metrics,
                "verdict": verdict,
            }

            mesh_inp_bytes = mesh_inp.read_bytes()
            written = ["simulation/solver_log.txt", "simulation/results_summary.json", "simulation/mesh.inp"]
            if frd_bytes:
                written.append("simulation/result.frd")
            _write_results_to_package(package_path, solver_log, frd_bytes, results_summary, mesh_inp_bytes)

            sim_result: dict[str, Any] = {
                "status": status,
                "project_id": project_id,
                "returncode": returncode,
                "von_mises_max_mpa": von_mises_max,
                "displacement_max_mm": displacement_max,
                "node_count": node_count,
                "mesh_size_mm": mesh_size_mm,
                "written_artifacts": written,
                "warnings": warnings,
                "verdict": verdict,
            }
            if returncode != 0:
                sim_result["solver_log_tail"] = solver_log[-2000:]
                sim_result["diagnosis"] = _diagnose_solver_log(solver_log)

            done_msg = "Simulation complete" if status == "success" else f"Solver error (code {returncode})"
            yield _sse({"step": "done", "message": done_msg, "result": sim_result})

    except Exception as exc:
        yield _sse({"step": "error", "message": str(exc)})
