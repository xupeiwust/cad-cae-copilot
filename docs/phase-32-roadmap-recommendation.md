# Phase 32 — Roadmap Recommendation

> **Status: superseded — recommendation acted on.** Phase 32 deliverables
> have landed. The current follow-on is stronger real-output assertions,
> claim/evidence linkage, and a UI walkthrough — not implementing Phase 32
> itself. See `roadmap.md` → "Phase 32 — Real-Environment CAE Demo Readiness
> ✅ Implemented" for the canonical record.
>
> **Landed artifacts:**
>
> - `aieng-ui/docs/quickstart-real-ccx.md` — real-environment quickstart;
>   now also includes a "Run the full real-pipeline smoke test" section.
> - `aieng-ui/backend/tests/fixtures/minimal_cantilever.inp` — 1-element
>   CalculiX fixture for the skip-gated smoke test.
> - `aieng-ui/backend/tests/test_api.py::test_run_solver_real_ccx_skipped_if_unavailable`
>   — exercises the real `ccx` subprocess path through the approval gate.
> - `aieng-ui/backend/tests/test_api.py::test_full_real_pipeline_step_to_summary`
>   — doubly-gated full pipeline: `cae.generate_mesh` → in-test deck
>   completion → `cae.run_solver` → `postprocess.refresh_cae_summary`, no
>   mocks anywhere.
> - `aieng-ui/README.md` — links the real-environment quickstart.
>
> Backend verification at landing: `175 passed, 3 skipped`. Boundary rules
> preserved — solver output and artifacts are evidence, not claims; claim
> advancement remains an explicit, separate workflow.
>
> The sections below are kept as historical rationale for *why* this work
> was prioritized. They are no longer a recommendation to act on.

## 1. What the MVP is strongest at

| Strength | Evidence |
|----------|----------|
| **End-to-end evidence-backed workflow** | `test_vertical_cae_workflow_end_to_end` exercises read → preflight → approval-gated execution → extract → refresh → report with enforced honesty boundaries (`converged: null`, explicit `limitations`, stale-artifact tracking). |
| **Runtime safety architecture** | Approval gates (`requires_approval=True`), ordered `RuntimeEvent` timeline, atomic ZIP artifact write-back, and structured `ToolCall`/`ToolResult` models. |
| **Agent-facing contract** | MCP bridge + Skill (`aieng-cad-cae-copilot`) + validation checklist give Claude Code / Codex a clear, bounded tool contract. |
| **Documentation consistency** | Demo walkthrough, quickstart, agent workflow pattern, and skill docs all describe the same 6-step vertical flow with matching limitations. |
| **Test coverage** | 111 backend tests pass; vertical benchmark enforces a 6-point honesty checklist. |

## 2. Biggest remaining gaps

| Gap | Severity | Why |
|-----|----------|-----|
| **Real-environment demo readiness** | High | The vertical benchmark mocks `ccx` entirely (`shutil.which` patched, `subprocess.run` side-effected). A teammate who installs the repo cannot actually run a real solver without manually finding/installing CalculiX and preparing a real `.inp`. |
| **Input deck acquisition path** | Medium | The system can run a solver if a deck exists, but generating or importing one into the workbench is not a runtime tool. The `aieng import-cae-deck` CLI exists but is not exposed through the runtime. |
| **File size / maintainability** | Medium | `main.py` ~3,300 lines, `test_api.py` ~3,500 lines, `App.tsx` ~2,500 lines. Future conflict and review cost is growing. |
| **UI product polish** | Low | Artifact inspector and diff viewer are minimal but functional. No blocker for a demo. |

## 3. Recommended next phase: A — Real-environment demo readiness *(historical)*

This was the recommendation at the time the doc was written. It has since been
implemented; see the status box at the top.

**Why A was chosen over B/C/D (preserved for historical reference):**

- The instruction boundary says: *"Avoid adding new engineering capabilities before the demo/workflow is understandable and reproducible."*
- The most impressive part of the system (approval-gated external solver execution) is currently only demonstrable by reading Python test mocks. A real-environment demo unlocks the most value per unit of work.
- Option B (engineering expansion) would add capabilities before the existing ones are demonstrable to a human reviewer.
- Option C (refactor) is valuable but does not move the product forward for users or reviewers.
- Option D (UI polish) is nice-to-have; the current UI is already sufficient for a demo.

## 4. What to explicitly avoid next

- **Do not** add mesh generation, input deck generation from geometry, or CAD parameter editing.
- **Do not** perform large refactors of `main.py`, `test_api.py`, or `App.tsx`.
- **Do not** add rich JSON graph visualization, live SSE events, or dependency-heavy diff libraries.
- **Do not** change `aieng` core schema or add new runtime tool contracts.
- **Do not** claim convergence or physical correctness even in a real solver demo — honest boundaries must remain.

## 5. Smallest concrete implementation plan *(historical — implemented)*

### Phase 32 — Real-environment vertical CAE demo readiness

The original deliverables below have all landed. See the status box at the top
of this file for the corresponding committed artifacts.

**Deliverables (as originally proposed):**

1. **Real-environment quickstart doc** (`aieng-ui/docs/quickstart-real-ccx.md`)
   - Where to get CalculiX (`ccx`) on Windows (binaries, WSL, or Docker).
   - How to prepare a minimal `.aieng` package with a real `.inp` deck.
   - How to run `cae.prepare_solver_run` and `cae.run_solver` without mocks.
   - Expected honest output (`converged: null`, limitations, etc.).

2. **Minimal real CalculiX fixture**
   - A tiny cantilever or bracket `.inp` deck (2–8 elements, runs in < 5 s).
   - Stored in `aieng-ui/backend/tests/fixtures/` or `examples/`.
   - This becomes the "hello world" of the real solver adapter.

3. **Backend test that exercises real ccx when available**
   - `test_run_solver_real_ccx_skipped_if_unavailable`
   - Skips gracefully with `pytest.mark.skipif(shutil.which("ccx") is None, ...)`.
   - If `ccx` is found, runs the fixture deck through the real adapter, asserts `solver_execution_performed=true`, and verifies the real `result.frd` is written into the package.
   - No mocks; uses the actual `subprocess.run` code path.

4. **README update**
   - Point to the new real-environment quickstart alongside the existing mocked quickstart.

**Files likely to change:**
- `aieng-ui/docs/quickstart-real-ccx.md` (new)
- `aieng-ui/backend/tests/fixtures/minimal_cantilever.inp` (new)
- `aieng-ui/backend/tests/test_api.py` (new test)
- `aieng-ui/README.md` (one-line link update)

**Validation commands:**
```powershell
cd /path/to/workspace_aieng\aieng-ui\backend
python -m pytest tests/test_api.py::test_run_solver_real_ccx_skipped_if_unavailable -v
```

**Risks / mitigations:**

| Risk | Mitigation |
|------|------------|
| CalculiX hard to install on Windows | Document multiple paths (Windows binaries, WSL, conda-forge). The test skips if unavailable, so CI is unaffected. |
| Real solver slower than mocks | Use a 2–8 element mesh; expect < 5 s execution. |
| Test flakiness on CI | `skipif` guard ensures the test never fails on CI; it only runs when a human has explicitly installed `ccx`. |

**Expected outcome:**
A teammate can install CalculiX, run one pytest command, and see the approval gate pause before a real external solver execution — then inspect the real FRD artifact in the Artifact Inspector. The mocked benchmark remains for CI; the real test proves the adapter works with actual software.
