# `.aieng` Package Semantics

## Positioning

`.aieng` is an auditable engineering context package for AI-assisted CAD/CAE
workflows. The `aieng` core repo owns pure package semantics: callers supply
already-read paths, bytes, and dictionaries, and the core returns structured
objects that make package state reviewable. It does not open ZIP files, call
HTTP endpoints, run CAD kernels, run solvers, or certify engineering claims.

The reference runtime (`aieng-ui`) owns ZIP/project I/O, FastAPI endpoints,
filesystem interaction, tool execution, and orchestration. Runtime code should
delegate package-level semantic decisions to the core helpers documented here.

```text
CAD/CAE artifacts
  -> converters/adapters
  -> .aieng package
  -> evidence + audit + freshness + proposals
  -> human/agent review
```

For a minimal in-memory walkthrough, see
[`examples/package_semantics_cookbook.py`](../examples/package_semantics_cookbook.py).
It uses direct submodule imports and requires no FreeCAD, CalculiX, `.aieng`
ZIP, `aieng-ui`, or network access. For release scope and blockers, see
[`release-v0.1-alpha-checklist.md`](release-v0.1-alpha-checklist.md).

## Core concepts

- **Artifact**: A package-internal file such as `geometry/source.step`,
  `results/evidence_index.json`, `results/fields/displacement.summary.json`,
  `claims/proposals/<id>.json`, or `audit/events.jsonl`. Artifact paths are
  classified by `aieng.package_manifest`.
- **Artifact manifest**: A structured inventory generated from package paths.
  It records each artifact's kind, category, producer tool when known, evidence
  role when known, and freshness context for categories affected by geometry
  edits. The manifest is descriptive; every entry keeps
  `claim_advancement: "none"`.
- **Evidence**: A traceable package artifact that may support review. Evidence
  can be present, missing, indexed, fresh, or stale. Evidence is not a claim:
  resolving evidence does not assert that an engineering claim is true.
- **Evidence index**: A catalog of evidence entries and their roles/supports.
  The resolver can use it along with package paths to decide whether a reference
  is resolvable.
- **Audit event**: An append-only observational event record describing what a
  tool did, which artifacts it wrote, which evidence it created, and what state
  changed. Audit events do not accept or advance claims.
- **Revalidation status**: The geometry freshness state. It tracks the current
  geometry revision, last solver-validated geometry revision, whether
  downstream CAE artifacts require revalidation, the stale-since revision, and
  the solver run that cleared stale state. Freshness is not validation.
- **Geometry revision**: A monotonic counter incremented by geometry-edit
  transitions. Solver validation records which geometry revision was validated.
- **CAE result summary**: An LLM-readable summary of CAE/post-processing
  artifacts. It orients reviewers to available outputs and limitations; it does
  not run a solver or certify the result.
- **Field summary**: A compact field-evidence artifact such as displacement or
  stress extrema. It can support review without requiring a runtime to load full
  numerical fields.
- **Claim proposal**: A draft artifact proposing a status such as `supported`,
  `not_supported`, or `needs_review` for a claim. Proposal is not acceptance:
  proposals do not create claim maps and keep `claim_advancement: "none"`.
- **Review readiness**: A rollup over a proposal's evidence references,
  missing/stale counts, proposal status, and claim-map absence. It answers
  whether a proposal is ready to review, warning, or blocked. Diagnostics are
  not certification.
- **Claim support packet**: A read-only assembly of one proposal, resolved
  supporting evidence, related audit events, and review readiness. It makes
  review context portable without accepting or rejecting the proposal.
- **Package consistency diagnostic**: A fixed set of package health checks over
  pre-read package data: evidence paths, audit references, field-summary
  sources, revalidation consistency, claim-map absence, and claim proposal
  well-formedness. A clean diagnostic makes the package easier to review; it is
  not automatic engineering validation.
- **Runtime capability profile**: When present, runtime/tool capability metadata
  describes what adapters or tools can do. It belongs to orchestration and
  integration boundaries, not to claim acceptance.

## Modules and ownership

### `aieng.package_manifest`

Classifies artifact paths into kinds, categories, producer tools, and evidence
roles using a deterministic pattern catalog. Generates artifact manifests from
path lists supplied by the caller.

Key exports: `classify_artifact_path`, `generate_artifact_manifest`,
`ARTIFACT_MANIFEST_PATH`, `FRESHNESS_CATEGORIES`.

### `aieng.evidence_resolver`

Resolves one evidence reference against package paths, evidence-index entries,
and revalidation status. It reports existence, index membership, freshness
warnings, geometry revisions, usability for a proposal, and
`claim_advancement: "none"`.

Key exports: `resolve_evidence_reference`, `STALE_EVIDENCE_CATEGORIES`.

### `aieng.package_consistency`

Runs package consistency diagnostics over caller-supplied raw bytes and parsed
state. It does not read ZIPs or mutate packages.

Key exports: `run_package_consistency_checks`, `rollup_check_status`,
`check_claim_map_absent`, `check_claim_proposals`, `is_internal_package_path`.

### `aieng.review_readiness`

Builds the five-check review readiness rollup for a claim proposal: supporting
evidence present, no missing evidence, stale evidence warning, proposal status
reviewable, and no claim map advanced.

Key export: `build_review_readiness`.

### `aieng.claim_proposal`

Owns claim proposal artifact construction, validation, path conventions, and
status vocabulary. It does not accept, reject, advance, or certify claims.

Key exports: `build_claim_proposal`, `validate_claim_proposal_request`,
`validate_claim_proposal_artifact`, `claim_proposal_path`,
`CLAIM_PROPOSAL_STATUSES`, `CLAIM_PROPOSAL_ARTIFACT_PREFIX`.

### `aieng.support_packet`

Assembles a stable read-only support packet from an already-built proposal,
already-resolved evidence references, already-filtered audit events, and
already-built review readiness. It does not read ZIPs, resolve evidence, or
inspect runtime project state.

Key export: `build_claim_support_packet`.

### `aieng.audit_event`

Owns audit event construction, validation, parsing, and JSONL serialization.
Every event carries `claim_advancement: "none"`.

Key exports: `build_audit_event`, `validate_audit_event`,
`parse_audit_events_jsonl`, `serialize_audit_events_jsonl`,
`AUDIT_EVENTS_PATH`, `AUDIT_EVENT_TYPES`.

### `aieng.revalidation_status`

Owns geometry revision state transitions: default state, geometry edit stale
transition, solver validation fresh transition, API response shaping, and
validation.

Key exports: `default_revalidation_status`, `record_geometry_edit_status`,
`record_solver_validation_status`, `build_revalidation_response`,
`validate_revalidation_status`, `REVALIDATION_STATUS_PATH`.

### `aieng.cae_result_summary`

Generates LLM-readable CAE/post-processing summaries, evidence indexes, and
markdown summaries from package content. Some legacy helpers read package ZIPs;
the newer package-semantics helpers above remain pure and are the preferred
surface for runtime-neutral semantics.

Key exports: `generate_cae_result_summary`, `generate_evidence_index`,
`generate_postprocessing_markdown`, `write_cae_result_summary_package`,
`RESULT_SUMMARY_PATH`, `EVIDENCE_INDEX_PATH`.

## Import pattern

Direct submodule imports are the stable public approach; top-level re-exports
are not required.

```python
from aieng.audit_event import build_audit_event
from aieng.claim_proposal import build_claim_proposal
from aieng.evidence_resolver import resolve_evidence_reference
from aieng.package_consistency import run_package_consistency_checks
from aieng.package_manifest import generate_artifact_manifest
from aieng.revalidation_status import record_geometry_edit_status
from aieng.review_readiness import build_review_readiness
```

Each submodule declares `__all__` for its stable public surface.

## What `.aieng` is not

- Not a CAD kernel.
- Not a mesh generator.
- Not a solver.
- Not a certification system.
- Not automatic engineering validation.
- Not proof that STEP contains design intent.
- Not a mechanism for silent claim acceptance, rejection, or advancement.

## Where conversion fits

Converters are ingestion adapters. They bring CAD/CAE artifacts into a package
so the higher-value layer can make state explicit: evidence, provenance,
freshness, audit history, proposal discipline, and review readiness. Conversion
is important plumbing, but the package semantics are the central contract: they
separate geometry from intent, inference from evidence, evidence from claims,
proposals from acceptance, and diagnostics from certification.

## Claim-safety invariant

`claim_advancement: "none"` remains the default invariant. Tool execution,
artifact generation, audit logging, consistency checks, evidence resolution,
review readiness, and revalidation transitions must not silently advance
engineering claims. A future explicit claim-acceptance workflow would need to be
added deliberately and reviewed as a separate semantic layer.
