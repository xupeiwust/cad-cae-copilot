# AIENG Copilot MVP Gap Analysis

Status: **v0.34**
Last updated: **2026-05-19**

## What AIENG can do now (MVP)

| Capability | Status |
|---|---|
| Project Health Check (15 checks, SHA-256 mutation guard) | ✅ |
| Health-to-Action Guidance | ✅ |
| Design Targets Authoring & Import | ✅ |
| Computed Metrics Import + Target Mapping | ✅ |
| Target Comparison Engine v1 | ✅ |
| FreeCAD read-only inspection | ✅ |
| Approval-gated FreeCAD parameter edit | ✅ |
| Structural adapter readiness + preflight | ✅ |
| Approval-gated structural solver run | ✅ |
| FRD/DAT extraction → computed metrics | ✅ |
| Target comparison refresh with solver data | ✅ |
| Copilot Loop report | ✅ |
| Engineering Review Support Packet | ✅ |
| Contextual approval panels | ✅ |
| Copilot Loop workflow sections | ✅ |
| Parametric CAD + FEA setup template authoring (drafts) | ✅ |

### Near-term controlled template capability (v0.35–v0.40)

| Capability | Status |
|---|---|
| Template draft → design targets handoff | 🔜 Planned (#14) |
| Template → safe CAD generation fixture | 🔜 Planned (#15) |
| Template → solver deck draft | 🔜 Planned (#16) |
| Multi-load-case target comparison | 🔜 Planned (#17) |
| Batch approval workflow | 🔜 Planned (#18) |
| Review Packet v1.1 (downloadable bundle) | 🔜 Planned (#19) |
| **Natural Language Intent Planner v1** | **🔜 Planned (#23)** |

**Verification:** 563 backend tests passed, 3 skipped. Frontend build passes.

## What AIENG cannot do yet

| Capability | Gap | Complexity |
|---|---|---|
| Arbitrary text-to-CAD | Controlled templates only; no free-form generation | High |
| Automatic preprocessing (mesh generation) | Mesh is manual or template-scoped; no automatic mesh-from-CAD | Medium |
| Multi-load-case simulation | Single load case per run; no batch workflow | Medium |
| CFD / OpenFOAM | No adapter; research-only (v0.41) | High |
| Collaboration / role-based review | Single user; no reviewer/approver roles | Medium |
| Commercial-grade platform maturity | No SSO, RBAC, audit log retention policy, SLA | High |
| Generalized CAD feature editing | Single parameter edits only; no sketch/feature creation | High |
| Automatic optimization / topology optimization | No optimization loop; proposals are hypotheses only | High |
| Multi-physics coupling | Structural only; no thermal, fluid-structure interaction | High |
| Commercial solver support (ANSYS, Abaqus, etc.) | CalculiX only | Medium |

## Distinguishing current, near-term, and future

### Current MVP (v0.29–v0.34)
- Single structural load case.
- Controlled parametric templates (drafts only, no execution).
- FreeCAD parameter edit (single parameter, approval-gated).
- CalculiX solver (approval-gated, FRD extraction).
- Human-in-the-loop at every mutation.

### Near-term controlled template capability (v0.35–v0.40)
- Template draft → design targets handoff.
- Template → safe CAD generation fixture (controlled, deterministic).
- Template → solver deck draft (controlled, deterministic).
- Multi-load-case comparison.
- Batch approval workflow (explicit per-batch approval).
- Review Packet v1.1 (downloadable bundle).

### Future generalized automation (v0.41+)
- OpenFOAM / CFD preflight + artifact viewer (v0.41–v0.43).
- CFD execution (v0.44+, deferred until structural path is hardened).
- Arbitrary text-to-CAD (requires stronger validation; out of MVP).
- Automatic optimization (out of MVP; proposals remain hypotheses).
- Multi-physics (out of MVP).

## Honest limitations

1. **FreeCAD is optional** — preflight reports missing dependencies honestly.
2. **CalculiX is optional** — solver unavailable path is tested and honest.
3. **Templates are controlled** — not arbitrary text-to-CAD.
4. **Approval is required** — no autonomous mutation or solver execution.
5. **Evidence ≠ certification** — AIENG produces evidence for human review.
6. **Single user** — no collaboration, review roles, or approval chains.
7. **Small fixtures** — tested on bracket/cantilever scales; large models untested.

## What is required for each future capability

### Arbitrary text-to-CAD
- Robust validation of generated CAD scripts.
- Sandboxed execution environment.
- Rollback on validation failure.
- Human review of every generated feature.

### Automatic preprocessing
- Mesh quality metrics and thresholds.
- Automatic mesh → solver deck pipeline.
- Validation of mesh completeness.

### Multi-load-case simulation
- Batch execution framework.
- Per-load-case result isolation.
- Aggregate comparison logic.

### CFD / OpenFOAM
- Case setup validation.
- Convergence detection.
- Boundary condition verification.
- Turbulence model selection guidance.
- Post-processing metric extraction.

### Collaboration / role-based review
- User authentication.
- Role definitions (engineer, reviewer, approver).
- Audit trail per user action.
- Approval chain logic.

### Commercial-grade maturity
- SSO integration.
- RBAC.
- Audit log retention.
- Data backup / recovery.
- SLA guarantees.
