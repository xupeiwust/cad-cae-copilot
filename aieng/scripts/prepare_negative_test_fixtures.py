"""
Generate four deliberately-broken .aieng packages for Phase 18C negative tests.

Each package is designed so that `aieng validate` or `aieng ref-check` produces a
predictable FAIL message.  The script reports the expected failure for each fixture.

Negative test fixtures
----------------------
1. dangling_ref
   - claim_map.json has `actual_evidence_ids: ["ev_NONEXISTENT_999"]`
   - `aieng ref-check` must FAIL: "references unknown evidence ID 'ev_NONEXISTENT_999'"

2. auto_advance_true
   - claim_map.json has a claim with `decision_criteria.auto_advance: true`
   - `aieng validate` must FAIL: "decision_criteria.auto_advance must be false"

3. pass_no_evidence
   - claim_map.json has a solver/result_available claim with `verification_status: pass`
     but `actual_evidence_ids: []`
   - `aieng validate` must FAIL: "solver pass claim … must have actual_evidence_ids"

4. snapshot_as_evidence
   - claim_map.json has `actual_evidence_ids: ["ai/summary.md"]` (a path, not an ID)
   - `aieng ref-check` must FAIL: "has forbidden evidence target 'ai/summary.md'"
"""
from __future__ import annotations

import copy
import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(REPO_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

BASE_PACKAGE = REPO_ROOT / "build" / "plate_with_pattern_001_rich.aieng"
OUT_DIR = REPO_ROOT / "build" / "negative_tests"
RUN_DIR = REPO_ROOT / "benchmark_runs" / "plate_with_pattern_001" / "negative_tests"

# ── helpers ───────────────────────────────────────────────────────────────────


def _read_all(zf: zipfile.ZipFile) -> dict[str, bytes]:
    """Return {name: bytes} for all members of a zip."""
    return {name: zf.read(name) for name in zf.namelist()}


def _write_package(out_path: Path, members: dict[str, bytes]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _patch_json(members: dict[str, bytes], key: str, patcher: object) -> dict[str, bytes]:
    """Return a shallow copy of *members* with members[key] replaced by patcher(data)."""
    data = json.loads(members[key])
    patched = patcher(data)  # type: ignore[operator]
    result = dict(members)
    result[key] = json.dumps(patched, indent=2).encode()
    return result


# ── individual fixture builders ───────────────────────────────────────────────


def _make_dangling_ref(members: dict[str, bytes]) -> dict[str, bytes]:
    """
    Inject a reference to a non-existent evidence ID into the first claim.
    Expected failure: ref-check FAIL "references unknown evidence ID 'ev_NONEXISTENT_999'"
    """

    def patch(data: dict) -> dict:
        data = copy.deepcopy(data)
        if data.get("claims"):
            data["claims"][0]["actual_evidence_ids"] = ["ev_NONEXISTENT_999"]
        return data

    return _patch_json(members, "results/claim_map.json", patch)


def _make_auto_advance_true(members: dict[str, bytes]) -> dict[str, bytes]:
    """
    Set decision_criteria.auto_advance = true on the first claim that has decision_criteria.
    Expected failure: validate FAIL "decision_criteria.auto_advance must be false"
    """

    def patch(data: dict) -> dict:
        data = copy.deepcopy(data)
        for claim in data.get("claims", []):
            dc = claim.get("decision_criteria")
            if isinstance(dc, dict):
                dc["auto_advance"] = True  # violates schema enum [false] + validator rule
                break
        return data

    return _patch_json(members, "results/claim_map.json", patch)


def _make_pass_no_evidence(members: dict[str, bytes]) -> dict[str, bytes]:
    """
    Add a solver/result_available claim with verification_status=pass but empty evidence.
    Expected failure: validate FAIL "solver pass claim … must have actual_evidence_ids"
    """

    def patch(data: dict) -> dict:
        data = copy.deepcopy(data)
        fake_solver_claim = {
            "claim_id": "claim_solver_result_fake_001",
            "claim_type": "solver/result_available",
            "claim_text": "Static structural analysis has been completed and results are available.",
            "required_evidence_ids": ["ev_solver_result_001"],
            "actual_evidence_ids": [],  # deliberately empty — no evidence attached
            "verification_status": "pass",  # falsely marked pass
            "notes": "DELIBERATE NEGATIVE TEST: status=pass with no evidence.",
            "decision_criteria": {
                "pass_requires": "solver result evidence present",
                "auto_advance": False,
                "unsupported_if": "no solver_result evidence",
            },
        }
        data["claims"].append(fake_solver_claim)
        return data

    return _patch_json(members, "results/claim_map.json", patch)


def _make_snapshot_as_evidence(members: dict[str, bytes]) -> dict[str, bytes]:
    """
    Set actual_evidence_ids to a path-like string (ai/summary.md) instead of an evidence ID.
    Expected failure: ref-check FAIL "has forbidden evidence target 'ai/summary.md'"
    """

    def patch(data: dict) -> dict:
        data = copy.deepcopy(data)
        if data.get("claims"):
            data["claims"][0]["actual_evidence_ids"] = ["ai/summary.md"]
        return data

    return _patch_json(members, "results/claim_map.json", patch)


# ── main ──────────────────────────────────────────────────────────────────────

FIXTURES: list[tuple[str, object, str, str]] = [
    (
        "dangling_ref",
        _make_dangling_ref,
        "ref-check",
        "references unknown evidence ID 'ev_NONEXISTENT_999'",
    ),
    (
        "auto_advance_true",
        _make_auto_advance_true,
        "validate",
        "decision_criteria.auto_advance must be false",
    ),
    (
        "pass_no_evidence",
        _make_pass_no_evidence,
        "validate",
        "solver pass claim 'claim_solver_result_fake_001' must have actual_evidence_ids",
    ),
    (
        "snapshot_as_evidence",
        _make_snapshot_as_evidence,
        "ref-check",
        "has forbidden evidence target 'ai/summary.md'",
    ),
]


def main() -> int:
    if not BASE_PACKAGE.exists():
        print(
            f"negative-tests: base package not found: {BASE_PACKAGE}\n"
            "Run scripts/prepare_plate_with_pattern_benchmark_pack.py first."
        )
        return 1

    with zipfile.ZipFile(BASE_PACKAGE) as zf:
        base_members = _read_all(zf)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    print("negative-tests: generating fixtures from", BASE_PACKAGE.name)
    for name, builder, check_tool, expected_msg in FIXTURES:
        out_path = OUT_DIR / f"negative_{name}.aieng"
        members = builder(base_members)  # type: ignore[operator]
        _write_package(out_path, members)
        print(f"  WROTE  {out_path.relative_to(REPO_ROOT)}")
        print(f"         expected failure ({check_tool}): {expected_msg!r}")

    _write_readme(RUN_DIR)
    print(f"\nnegative-tests: README written to {(RUN_DIR / 'README.md').relative_to(REPO_ROOT)}")
    print("\nVerify with:")
    for name, _, check_tool, _ in FIXTURES:
        pkg = f"build/negative_tests/negative_{name}.aieng"
        if check_tool == "ref-check":
            print(f"  aieng ref-check {pkg}")
        else:
            print(f"  aieng validate  {pkg}")
    return 0


def _write_readme(out_dir: Path) -> None:
    text = """\
# Negative Test Fixtures — Phase 18C

These packages are **deliberately broken** to verify that `aieng validate` and
`aieng ref-check` produce the correct FAIL messages.  They should **not** be
used as benchmark inputs for AI evaluation.

| Fixture | Expected tool | Expected FAIL fragment |
|---------|--------------|------------------------|
| `negative_dangling_ref.aieng` | `aieng ref-check` | `references unknown evidence ID 'ev_NONEXISTENT_999'` |
| `negative_auto_advance_true.aieng` | `aieng validate` | `decision_criteria.auto_advance must be false` |
| `negative_pass_no_evidence.aieng` | `aieng validate` | `solver pass claim … must have actual_evidence_ids` |
| `negative_snapshot_as_evidence.aieng` | `aieng ref-check` | `has forbidden evidence target 'ai/summary.md'` |

## Source

All fixtures are generated from `build/plate_with_pattern_001_rich.aieng` by
`scripts/prepare_negative_test_fixtures.py`.

## Regeneration

```powershell
$env:PYTHONPATH='src'
python scripts/prepare_negative_test_fixtures.py
```

## Verification commands

```powershell
$env:PYTHONPATH='src'
# 1 – dangling_ref  → ref-check FAIL
python -m aieng.cli ref-check build/negative_tests/negative_dangling_ref.aieng

# 2 – auto_advance_true  → validate FAIL
python -m aieng.cli validate build/negative_tests/negative_auto_advance_true.aieng

# 3 – pass_no_evidence  → validate FAIL
python -m aieng.cli validate build/negative_tests/negative_pass_no_evidence.aieng

# 4 – snapshot_as_evidence  → ref-check FAIL
python -m aieng.cli ref-check build/negative_tests/negative_snapshot_as_evidence.aieng
```

## Design rationale

| # | Defect class | What it tests |
|---|-------------|---------------|
| 1 | Dangling evidence reference | ref-check cross-resource ID resolution |
| 2 | auto_advance policy violation | Validator enforcement of evidence-only policy |
| 3 | Pass claim without evidence | Validator rule: solver/mesh/geometry claims need real evidence |
| 4 | Snapshot path in evidence slot | ref-check forbidden evidence target detection |
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
