"""Geometry target validator v0 (#291).

Deterministic, spec-driven checks of the exact geometric promises in a modeling
brief — so an agent can't ship a plausible-looking but mispositioned or
over-modeled model. Operates purely on ``topology_map`` + ``feature_graph`` dicts
(no solver, no OCC kernel); every target yields pass / fail / unknown with the
measured vs expected values.

Honesty: ``unknown`` is used when the data needed to judge a target is absent
(never guessed). Bbox-based checks are axis-aligned bounding-box measurements,
not exact surface geometry — adequate for size/position/presence promises, not a
GD&T solver. ``no_deep_overlap`` is a bbox-overlap heuristic, opt-in per target.
"""
from __future__ import annotations

from typing import Any

TARGET_KINDS = (
    "named_part_present",
    "feature_present",
    "part_count",
    "overall_size",
    "part_size",
    "part_center",
    "no_floating_parts",
    "no_deep_overlap",
)


def _solids(topology_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        e for e in (topology_map or {}).get("entities", [])
        if isinstance(e, dict) and e.get("type") == "solid"
        and isinstance(e.get("bounding_box"), list) and len(e["bounding_box"]) == 6
    ]


def _solid_key(e: dict[str, Any]) -> str:
    return str(e.get("name") or e.get("id") or "")


def _size(bb: list[float]) -> tuple[float, float, float]:
    return (bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])


def _center(bb: list[float]) -> tuple[float, float, float]:
    return ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)


def _union(boxes: list[list[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [min(b[i] for b in boxes) for i in range(3)] + [max(b[i + 3] for b in boxes) for i in range(3)]


def _overlap_volume(a: list[float], b: list[float]) -> float:
    dims = [max(0.0, min(a[i + 3], b[i + 3]) - max(a[i], b[i])) for i in range(3)]
    return dims[0] * dims[1] * dims[2]


def _bbox_volume(bb: list[float]) -> float:
    s = _size(bb)
    return max(0.0, s[0]) * max(0.0, s[1]) * max(0.0, s[2])


def _bbox_gap(a: list[float], b: list[float]) -> float:
    """Max axis separation between two AABBs (negative ⇒ overlap on that axis)."""
    return max(max(a[i] - b[i + 3], b[i] - a[i + 3]) for i in range(3))


def _r3(v: tuple[float, float, float]) -> list[float]:
    return [round(v[0], 3), round(v[1], 3), round(v[2], 3)]


def _result(target: dict[str, Any], idx: int, status: str, detail: str,
            measured: Any = None, expected: Any = None) -> dict[str, Any]:
    return {
        "id": target.get("id") or f"target_{idx:03d}",
        "kind": target.get("kind"),
        "status": status,            # pass | fail | unknown
        "measured": measured,
        "expected": expected,
        "tolerance_mm": target.get("tolerance_mm"),
        "detail": detail,
    }


def validate_geometry_targets(
    topology_map: dict[str, Any],
    feature_graph: dict[str, Any],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate a list of geometry targets against the model. See module docstring."""
    solids = _solids(topology_map)
    by_name = {_solid_key(e): e for e in solids}
    union = _union([e["bounding_box"] for e in solids])
    features = (feature_graph or {}).get("features", [])
    feature_types = {str(f.get("type")) for f in features}
    named_parts = {str(f.get("name")) for f in features
                   if f.get("type") in {"named_part", "standard_part"} and f.get("name")}
    named_parts |= {_solid_key(e) for e in solids if e.get("name")}

    results: list[dict[str, Any]] = []
    for idx, t in enumerate(targets if isinstance(targets, list) else []):
        if not isinstance(t, dict):
            results.append(_result({}, idx, "unknown", "target is not an object"))
            continue
        kind = str(t.get("kind") or "")
        tol = float(t["tolerance_mm"]) if isinstance(t.get("tolerance_mm"), (int, float)) else 1.0

        if kind == "named_part_present":
            part = str(t.get("part") or "")
            ok = part in named_parts
            results.append(_result(t, idx, "pass" if ok else "fail",
                                    f"part '{part}' {'present' if ok else 'NOT present'}",
                                    measured=sorted(named_parts) if not ok else part, expected=part))

        elif kind == "feature_present":
            ft = str(t.get("feature_type") or "")
            ok = ft in feature_types
            results.append(_result(t, idx, "pass" if ok else "fail",
                                    f"feature type '{ft}' {'present' if ok else 'NOT present'}",
                                    measured=sorted(feature_types) if not ok else ft, expected=ft))

        elif kind == "part_count":
            n = len(solids)
            lo = t.get("min"); hi = t.get("max"); exact = t.get("count")
            ok = True
            if isinstance(exact, int):
                ok = n == exact
            if isinstance(lo, int):
                ok = ok and n >= lo
            if isinstance(hi, int):
                ok = ok and n <= hi
            results.append(_result(t, idx, "pass" if ok else "fail",
                                    f"{n} solid part(s)", measured=n,
                                    expected={"count": exact, "min": lo, "max": hi}))

        elif kind == "overall_size":
            exp = t.get("size_mm")
            if union is None or not (isinstance(exp, list) and len(exp) == 3):
                results.append(_result(t, idx, "unknown", "no solids or bad size_mm", expected=exp))
                continue
            sz = _size(union)
            dev = [abs(sz[i] - float(exp[i])) for i in range(3)]
            ok = all(d <= tol for d in dev)
            results.append(_result(t, idx, "pass" if ok else "fail",
                                    f"overall size {_r3(sz)} vs {exp} (tol {tol}); max dev {round(max(dev), 3)}mm",
                                    measured=_r3(sz), expected=exp))

        elif kind in ("part_size", "part_center"):
            part = str(t.get("part") or "")
            e = by_name.get(part)
            if e is None:
                results.append(_result(t, idx, "fail", f"part '{part}' not found", expected=part))
                continue
            bb = e["bounding_box"]
            measured = _size(bb) if kind == "part_size" else _center(bb)
            key = "size_mm" if kind == "part_size" else "center_mm"
            exp = t.get(key)
            if not (isinstance(exp, list) and len(exp) == 3):
                results.append(_result(t, idx, "unknown", f"bad {key}", expected=exp))
                continue
            dev = [abs(measured[i] - float(exp[i])) for i in range(3)]
            ok = all(d <= tol for d in dev)
            results.append(_result(t, idx, "pass" if ok else "fail",
                                    f"{part} {kind} {_r3(measured)} vs {exp} (tol {tol}); max dev {round(max(dev), 3)}mm",
                                    measured=_r3(measured), expected=exp))

        elif kind == "no_floating_parts":
            if len(solids) < 2:
                results.append(_result(t, idx, "pass", f"{len(solids)} part(s); nothing can float"))
                continue
            mean = sum(max(_size(e["bounding_box"])) for e in solids) / len(solids)
            thresh = max(mean, 50.0)
            floating = []
            for e in solids:
                gaps = [_bbox_gap(e["bounding_box"], o["bounding_box"]) for o in solids if o is not e]
                if gaps and min(gaps) > thresh:
                    floating.append(_solid_key(e))
            results.append(_result(t, idx, "pass" if not floating else "fail",
                                   "no floating parts" if not floating else f"floating: {floating}",
                                   measured=floating))

        elif kind == "no_deep_overlap":
            frac = float(t.get("max_overlap_fraction", 0.5))
            offenders = []
            for i in range(len(solids)):
                for j in range(i + 1, len(solids)):
                    a, b = solids[i]["bounding_box"], solids[j]["bounding_box"]
                    ov = _overlap_volume(a, b)
                    small = min(_bbox_volume(a), _bbox_volume(b)) or 1.0
                    if ov / small > frac:
                        offenders.append([_solid_key(solids[i]), _solid_key(solids[j]), round(ov / small, 3)])
            results.append(_result(t, idx, "pass" if not offenders else "fail",
                                   "no deep bbox overlaps" if not offenders
                                   else f"deep overlap (fraction>{frac}): {offenders}",
                                   measured=offenders))

        else:
            results.append(_result(t, idx, "unknown",
                                   f"unknown target kind '{kind}' (expected one of {list(TARGET_KINDS)})"))

    counts = {"pass": 0, "fail": 0, "unknown": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    verdict = "fail" if counts["fail"] else ("unknown" if counts["unknown"] and not counts["pass"] else
                                             ("incomplete" if counts["unknown"] else "pass"))
    return {
        "format": "aieng.geometry_target_validation",
        "format_version": "0.1",
        "verdict": verdict,
        "summary": {"total": len(results), **counts},
        "targets": results,
        "honesty": (
            "Deterministic bbox/topology checks of declared targets — not a GD&T solver. "
            "'unknown' means the data to judge the target was absent (not guessed). "
            "no_deep_overlap is an opt-in AABB-overlap heuristic."
        ),
    }
