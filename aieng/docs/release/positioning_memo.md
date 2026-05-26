# Positioning memo

## Purpose

This memo records the intended architecture-level positioning for `.aieng` as reviewed during alpha release preparation.

## 1. What `.aieng` is not

### Not CAD automation

`.aieng` does not execute CAD edits, meshing, solver runs, or manufacturing checks. It packages context for review and handoff; it does not perform the engineering operations themselves.

### Not CAD-to-JSON

Converters may ingest STEP, CalculiX, FreeCAD, or other artifacts into `.aieng`, but conversion is only the entry path. The architectural value is not a one-time translation into JSON-shaped files. The value is the persistent review layer built on top of those artifacts:

- provenance,
- evidence references,
- freshness state,
- missingness/unsupported-state recording,
- auditability.

### Not an AI agent

`.aieng` is not an autonomous agent, orchestration runtime, or decision-maker. It can be consumed by agents, but it is deliberately separate from the agent runtime so that evidence and review state remain inspectable outside any one agent stack.

### Not a PLM system

`.aieng` is narrower than PLM. It is not trying to be the enterprise system of record for change control, lifecycle governance, supplier management, or organizational approval flows. Its scope is review-oriented engineering context packaging.

### Not an engineering certification system

`.aieng` does not grant certification, approval, or validation authority. It can record that external tools produced artifacts or that freshness changed after a geometry edit, but it does not convert those records into certification semantics.

## 2. Core architectural value

The value of `.aieng` is that it makes engineering context reviewable.

### Provenance

The package can record where artifacts came from, which tool produced them, and which package members were written. This matters because AI review without provenance tends to collapse evidence and inference.

### Evidence

The package distinguishes between the presence of an artifact and the truth of an engineering claim. An evidence reference can be present, missing, stale, unsupported, or usable for proposal review without silently becoming a claim.

### Freshness

Geometry revisions and revalidation state matter because imported solver artifacts may become stale after design edits. The package treats freshness as a first-class state transition rather than an implicit assumption.

### Missingness

What is absent or unsupported is often as important as what is present. `.aieng` can carry explicit missingness and uncertainty instead of forcing tools or agents to guess.

### Reviewability

Audit events, review readiness, package consistency checks, and support packets make it easier for humans or agents to inspect a workflow honestly. The point is not autonomous completion; the point is bounded review.

## 3. Why the project avoids certain semantics

### No autonomous engineering approval

Engineering approval requires accountable review. `.aieng` can package context for that review, but it intentionally avoids semantics that would let a tool silently approve its own output.

### No solver authority

A solver output file, convergence flag, or imported summary is evidence about a workflow artifact. It is not, by itself, an authority grant. `.aieng` therefore treats imported results as review inputs, not automatic truth.

### No certification semantics

Certification language is intentionally avoided because it invites misuse. The package can record audit/provenance/freshness state, but the project does not intend those records to stand in for regulated or formal certification processes.

## 4. Architectural consequence for alpha scope

The clean alpha story is therefore the pure semantics layer:

- artifact manifests,
- evidence resolution,
- package consistency,
- review readiness,
- claim proposals,
- audit events,
- revalidation status,
- support-packet assembly,
- CAE result summaries.

Everything else should be described relative to that core, not as a replacement for it.

## 5. Conservative conclusion

`.aieng` is best understood as a review-oriented engineering context layer with strong evidence/provenance/freshness semantics. It is not an automation authority and should not be released or described as one.
