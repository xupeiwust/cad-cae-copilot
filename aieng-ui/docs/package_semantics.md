# `.aieng` Package Semantics and Taxonomy

This document defines the core concepts of the `.aieng` ZIP package format,
the runtime that reads and writes it, and the API layer that exposes it. Each
concept states what it is, what it is not, who writes it, who reads it, and
whether it can advance engineering claims.

For runtime orchestration details see [`runtime_architecture.md`](runtime_architecture.md).
For the full real-binary pipeline walkthrough see [`walkthrough-real-cae-pipeline.md`](walkthrough-real-cae-pipeline.md).

---

## Principles

These six sentences summarise the intentional boundaries of the current system.
Everything below unpacks them.

- **Geometry is not intent.** A STEP file describes shape. It says nothing about
  what the design is trying to achieve or whether the shape is correct.
- **Inference is not evidence.** An LLM-generated summary or one-line description
  is a convenience output, not a traceable engineering record.
- **Evidence is not claim.** A solver result, a field summary, or an evidence
  index entry is a measurement artifact. It does not assert that any engineering
  requirement is met.
- **Proposal is not acceptance.** A claim proposal records an intent to support
  a claim. It does not advance the claim. Claim advancement is a separate,
  explicit step that the current workflow does not implement.
- **Freshness is not validation.** A revalidation status of `requires_revalidation:
  false` means the most recent solver run targeted the current geometry revision.
  It does not mean the results are physically correct or independently validated.
- **Diagnostics are not certification.** Package consistency checks, review
  readiness scores, and support packets are auditing tools. They surface
  information for a human reviewer; they do not certify anything.

---

## Concepts

### Artifact

**What it is.** A named file stored inside the `.aieng` ZIP archive. Artifacts
are the atomic units of the package. Every piece of data — geometry, mesh,
solver output, results, metadata — is an artifact.

**What it is not.** An artifact is not a database row, a live object, or a
version-controlled file. It is a snapshot captured at the time it was written.

**Written by.** Runtime tools (`cae.run_solver`, `cad.edit_parameter`,
`postprocess.refresh_cae_summary`, etc.) via the atomic rewrite pattern
(read all → temp file → `shutil.move`).

**Read by.** API endpoints, test helpers, the artifact inspector endpoint
(`GET /api/projects/{id}/artifact?path=...`), and the evidence reference resolver.

**Advances claims.** No.

---

### Evidence

**What it is.** An artifact that carries a traceable record of a physical or
computational result. The key evidence artifacts are:

| Artifact path | Evidence role |
|---|---|
| `simulation/runs/*/outputs/result.frd` | Raw CalculiX output |
| `simulation/runs/*/solver_run.json` | Solver execution metadata |
| `results/computed_metrics.json` | Extracted scalar extrema |
| `results/fields/displacement.summary.json` | Displacement field compact summary |
| `results/fields/stress.summary.json` | Stress field compact summary |
| `results/result_summary.json` | LLM-readable CAE result summary |
| `results/evidence_index.json` | Auditable catalog of all CAE artifacts |

**What it is not.** Evidence is not a claim. Evidence does not assert that a
design requirement is satisfied. Evidence from a stale geometry state is still
evidence — it is labelled stale and remains in the package as an auditable
historical record.

**Written by.** `cae.run_solver` (FRD, solver_run.json),
`cae.extract_solver_results` (computed_metrics.json),
`postprocess.refresh_cae_summary` (result_summary.json, evidence_index.json,
field summaries).

**Read by.** `GET /api/projects/{id}/cae-result-summary`,
`GET /api/projects/{id}/cae-result-fields`,
`GET /api/projects/{id}/cae-result-fields/{name}`,
`GET /api/projects/{id}/artifact?path=...`, claim proposals, evidence reference
resolver.

**Advances claims.** No. `claim_advancement: "none"` appears in every artifact
and every API response that touches evidence.

---

### Evidence Index

**What it is.** `results/evidence_index.json` — a JSON catalog of all known
CAE artifacts in the package. Contains a static section (canonical paths whose
`exists` field reflects whether the file is actually in the ZIP) and a dynamic
section (solver run paths discovered by scanning the ZIP, since run IDs are
generated at runtime).

**What it is not.** The evidence index is not a claim map, not a validation
certificate, and not a complete inventory of every ZIP member. It covers the
canonical CAE evidence artifact paths.

**Written by.** `postprocess.refresh_cae_summary` via
`aieng.cae_result_summary.generate_evidence_index`.

**Read by.** `GET /api/projects/{id}/cae-result-summary`, the evidence
reference resolver, claim proposal creation.

**Advances claims.** No.

---

### Audit Event

**What it is.** A single append-only line in `audit/events.jsonl` inside the
package ZIP. Each event has a schema version, timestamp, event type (e.g.
`geometry_modified`, `solver_run_completed`, `claim_proposal_created`),
producing tool, affected artifact paths, evidence created, state changes, and
geometry revision at the time of the event.

**What it is not.** An audit event is not a command log, not a full diff of
artifact contents, and not a database transaction record. It is a lightweight
provenance breadcrumb.

**Written by.** `_append_audit_event_to_package` — called by
`cad.edit_parameter`, `cae.run_solver`, `postprocess.refresh_cae_summary`, and
`POST /api/projects/{id}/claim-proposals`.

**Read by.** `GET /api/projects/{id}/audit-events`, claim support packets
(related audit events section).

**Advances claims.** No.

---

### Artifact Manifest

**What it is.** An on-demand classification of every ZIP member by kind,
category, producer tool, and evidence role. Produced by scanning the package
namelist against the `_ARTIFACT_PATTERN_CATALOG` pattern table and enriched
with freshness context from the revalidation status. Exposed by
`GET /api/projects/{id}/artifact-manifest`.

**What it is not.** The artifact manifest is not stored inside the package. It
is computed fresh on each request. It is not the evidence index (the evidence
index is a stored artifact; the manifest is a derived read-only view).

**Written by.** Never written. Computed on demand.

**Read by.** API consumers; useful for tooling and agents that need a
machine-readable inventory of the package.

**Advances claims.** No.

---

### Revalidation Status

**What it is.** `state/revalidation_status.json` — a lightweight artifact
tracking whether the current geometry revision has been validated by a solver
run. Contains `requires_revalidation` (bool), `current_geometry_revision`
(monotonically incrementing int), `last_validated_geometry_revision` (int or
null), and `claim_advancement: "none"`.

Results are **fresh** when `current_geometry_revision == last_validated_geometry_revision`.
They are **stale** when `current > last_validated`.

**What it is not.** Revalidation status is not physical correctness evidence.
`requires_revalidation: false` does not mean the results are correct — only
that the most recent solver run targeted the current geometry state. No geometry
hashing is performed; the counter is provenance metadata, not a content hash.

**Written by.** `cad.edit_parameter` (increments `current_geometry_revision`,
sets `requires_revalidation: true`); `cae.run_solver` on `return_code == 0`
(sets `last_validated_geometry_revision = current`, clears `requires_revalidation`).

**Read by.** All CAE result read endpoints inject revalidation status into their
responses. The evidence reference resolver and claim support packets surface it
per evidence reference. Package consistency check C.

**Advances claims.** No.

---

### Geometry Revision

**What it is.** A monotonically incrementing integer stored in the revalidation
status artifact. It advances by 1 on every successful real geometry edit
(`cad.edit_parameter` with a real executor). It is zero-based (0 before any
recorded edit).

**What it is not.** A content hash, a semantic version, a diff, or a branch
pointer. Two packages with `current_geometry_revision: 3` are not guaranteed
to have the same geometry.

**Written by.** `cad.edit_parameter` via `_record_geometry_edit_in_package`.

**Read by.** Revalidation status responses, evidence reference resolver, audit
events.

**Advances claims.** No.

---

### CAE Result Summary

**What it is.** `results/result_summary.json` — a JSON artifact containing the
LLM-readable CAE post-processing summary. Includes computed extrema
(`max_displacement`, `max_von_mises_stress`), status flags (`has_results`,
`converged: null` — honest because CalculiX exit codes are not reliable
convergence evidence), and a brief LLM-generated description.

**What it is not.** The CAE result summary is not a validation certificate, not
a design review record, and not a claim. `converged: null` is an honest value;
convergence determination requires explicit analysis.

**Written by.** `postprocess.refresh_cae_summary`.

**Read by.** `GET /api/projects/{id}/cae-result-summary`, evidence index,
claim proposals.

**Advances claims.** No.

---

### Field Summary

**What it is.** A compact JSON artifact at
`results/fields/{field_name}.summary.json` (currently `displacement` and
`stress`) containing scalar extrema from `results/computed_metrics.json`.
Contains `schema_version`, `field_name`, `unit`, `source`, `stats`
(`max_value`; `min_value`/`node_count`/`values_finite` are null since full
arrays are not stored), `evidence_role`, and `claim_advancement: "none"`.

**What it is not.** A field summary is not a full per-node array. It does not
store or serve contour data. It is compact evidence, not a post-processing
result.

**Written by.** `postprocess.refresh_cae_summary` (second call after computed
metrics are present).

**Read by.** `GET /api/projects/{id}/cae-result-fields`,
`GET /api/projects/{id}/cae-result-fields/{name}`, evidence index, evidence
reference resolver.

**Advances claims.** No.

---

### Claim

**What it is.** A named engineering assertion about the design (e.g.
`structural_integrity`, `fatigue_life`). Claims live conceptually in
`ai/claim_map.json` or `results/claim_map.json`. The current workflow does
**not** create or write claim maps. No claim is advanced by any runtime tool,
API endpoint, or artifact write in the current implementation.

**What it is not.** A claim is not a proposal, not a result, not a CAE summary.
A claim is an assertion that a design requirement is met.

**Written by.** Nothing in the current workflow. Claim creation and advancement
are reserved for a future explicit claim-update workflow.

**Read by.** Nothing in the current workflow (claim maps do not exist in the
package). Package consistency check E (`_check_claim_map_absent`) and review
readiness check E (`claim_map_not_advanced`) verify absence.

**Advances claims.** Not applicable — claims do not exist yet.

---

### Claim Proposal

**What it is.** A draft artifact at `claims/proposals/{proposal_id}.json`
recording an intent to support (or not support, or request review of) a named
claim. Contains `proposal_id`, `claim_id`, `proposed_status` (one of
`supported`, `not_supported`, `needs_review`), `rationale`, `supporting_evidence`
(list of artifact paths), `status: "proposed"`, `created_at`, and
`claim_advancement: "none"`.

**What it is not.** A claim proposal is not an accepted claim. Creating a
proposal does not write or modify any claim map. A proposal is a structured
intent record, not a decision record.

**Written by.** `POST /api/projects/{id}/claim-proposals`.

**Read by.** `GET /api/projects/{id}/claim-proposals` (list),
`GET /api/projects/{id}/claim-proposals/{proposal_id}` (single),
`GET /api/projects/{id}/claim-proposals/{proposal_id}/support-packet`.

**Advances claims.** No.

---

### Support Packet

**What it is.** A read-only aggregation returned by
`GET /api/projects/{id}/claim-proposals/{proposal_id}/support-packet`. Combines
the proposal, resolved evidence references (each with existence check,
evidence-index status, classification, and stale/missing warnings), related
audit events (those that wrote the proposal artifact), stale/missing evidence
counts, and review readiness diagnostics.

**What it is not.** A support packet is not a review decision, not a claim, and
not a mutation. It is a read-only evidence assembly for human or agent review.

**Written by.** Nothing — computed on each request from the current package state.

**Read by.** Human reviewers, agents performing pre-claim-advancement checks.

**Advances claims.** No. `claim_advancement: "none"` appears in the top-level
response, in each resolved evidence reference, and in the review readiness
object.

---

### Review Readiness

**What it is.** A sub-object inside the support packet (`review_readiness`)
containing a status rollup (`ready`, `warning`, or `blocked`) and five checks:

| Check ID | Blocks? | Meaning |
|---|---|---|
| `supporting_evidence_present` | Yes (blocked) | Proposal has ≥ 1 declared evidence path |
| `no_missing_evidence` | Yes (blocked) | All declared paths exist in package or evidence index |
| `stale_evidence` | No (warning) | Evidence not from a stale geometry state |
| `proposal_status_reviewable` | No (warning) | Proposal status is `proposed` or `draft` |
| `claim_map_not_advanced` | Yes (blocked) | No claim map present in package |

Rollup semantics: `blocked > warning > ready`. Stale evidence warns but does
not block — historical evidence from a prior geometry state is still valid
evidence; it is just labelled as stale.

**What it is not.** Review readiness is not a certification, not a compliance
gate, and not a claim advancement decision. A `ready` status means the proposal
is structurally complete enough for human review; it does not mean the claim is
correct.

**Written by.** `_build_review_readiness` — computed on demand inside
`_build_claim_support_packet`.

**Read by.** Support packet consumers.

**Advances claims.** No.

---

### Package Consistency Diagnostic

**What it is.** A set of health checks run against a package by
`GET /api/projects/{id}/package-consistency`. Currently covers six checks:

| Check ID | Meaning |
|---|---|
| `evidence_paths_exist` | CAE result paths in evidence index are present in ZIP |
| `audit_artifact_refs` | Artifact paths in audit events are present in ZIP |
| `field_summary_sources` | Field summary source artifacts exist |
| `revalidation_consistency` | Revalidation status is internally consistent |
| `claim_map_absent` | No claim map artifact exists |
| `claim_proposals_valid` | Claim proposal artifacts are parseable JSON |

Status rollup: `error > warning > ok`. Stale revalidation state is a `warning`,
not an `error`.

**What it is not.** Package consistency checks are not physical correctness
checks, not schema compliance validators, and not certification gates. They
surface structural inconsistencies that a human reviewer should know about.

**Written by.** Never written. Computed on demand.

**Read by.** API consumers.

**Advances claims.** No.

---

### Runtime Capability Profile

**What it is.** A static, machine-readable JSON profile returned by
`GET /api/runtime/capabilities`. Lists every registered tool with its
implementation status, availability (e.g. `ccx_available`,
`freecad_available`), approval requirement, and declared artifact write paths.

**What it is not.** The capability profile is not a runtime state snapshot.
It does not report whether any run is currently executing. `available: true`
means the binary dependency is present; it does not mean a run will succeed.

**Written by.** Never written. Computed from the tool registry and environment
probes at request time.

**Read by.** Agents and integrations that need to know what the workbench can
do before submitting a run.

**Advances claims.** No.

---

## Lifecycle flow

The table below summarises the happy-path artifact lifecycle. Every arrow is a
real runtime tool call; every artifact carries `claim_advancement: "none"`.

```
[Upload STEP geometry]
        │  manifest.json, geometry/source.step
        ▼
cad.edit_parameter (approval-gated, real executor)
        │  state/revalidation_status.json (requires_revalidation: true)
        │  audit/events.jsonl ← geometry_modified event
        ▼
cae.generate_mesh (approval-gated)
        │  simulation/mesh/mesh_*.inp
        │  simulation/mesh/mesh_metadata.json
        ▼
[Solver deck import / POST /solver-input]
        │  simulation/runs/{id}/solver_input.inp
        ▼
cae.run_solver (approval-gated)
        │  simulation/runs/{id}/solver_run.json  (converged: null)
        │  simulation/runs/{id}/solver_log.txt
        │  simulation/runs/{id}/outputs/result.frd
        │  results/computed_metrics.json  (if extract_results=True)
        │  state/revalidation_status.json (requires_revalidation: false)
        │  audit/events.jsonl ← solver_run_completed event
        ▼
postprocess.refresh_cae_summary
        │  results/result_summary.json
        │  results/evidence_index.json
        │  results/postprocessing_summary.md
        │  results/fields/displacement.summary.json
        │  results/fields/stress.summary.json
        │  audit/events.jsonl ← cae_summary_refreshed event
        ▼
POST /api/projects/{id}/claim-proposals
        │  claims/proposals/{proposal_id}.json
        │  audit/events.jsonl ← claim_proposal_created event
        ▼
GET /api/projects/{id}/claim-proposals/{id}/support-packet
        │  [read-only aggregation — no writes]
        │  review_readiness.status = "ready" if all checks pass

No claim map is written at any point.
Claim advancement is a separate, future workflow.
```

---

## What is never written

The following paths are intentionally absent from the current workflow. Their
absence is verified by package consistency check E and review readiness check E.

| Path | Why absent |
|---|---|
| `ai/claim_map.json` | Claim advancement is not implemented |
| `results/claim_map.json` | Claim advancement is not implemented |

If either path appears in the package, a consistency check error is raised.

---

## References

- [`runtime_architecture.md`](runtime_architecture.md) — orchestration layer, tool adapters, stale-state handling, revalidation workflow
- [`walkthrough-real-cae-pipeline.md`](walkthrough-real-cae-pipeline.md) — real-binary end-to-end pipeline and evidence vs. claims discipline
- [`quickstart-vertical-cae-demo.md`](quickstart-vertical-cae-demo.md) — mocked benchmark (no FreeCAD or ccx required)
- [`../../docs/package_contract.md`](../../docs/package_contract.md) — `.aieng` ZIP format and package states
