# Release blocker semantic audit

Scope scanned: `README.md`, `docs/`, `examples/`, `src/`, and `tests/`.

This report lists release-relevant wording or surfaces that conflict with the current alpha positioning:

- `.aieng` is an auditable CAD/CAE context package.
- It is not an engineering certification or automatic validation system.
- It should not expose claim-map or claim-advancement semantics in the `v0.1.0-alpha.1` story.

Notes:
- Plain package/schema validation text was **not** flagged unless it risks being read as engineering validation.
- The largest finding is not one sentence but a repeated legacy surface: `results/claim_map.json`, `update-claim`, and related read/write flows still appear across CLI, docs, MCP, and tests.

## Re-run status — 2026-06-13, current `main` (issue #181)

The baseline findings below were re-verified against current `main`. **The dominant
blocker — the legacy claim-map / `update-claim` surface — is resolved.** Each original
finding's status, with the verification anchor on current `main`:

| # | Original finding | Status on `main` | Evidence |
|---|---|---|---|
| B1 | `cli.py` writes `results/claim_map.json` | **Resolved** | No `claim_map.json` write text in `src/aieng/cli.py`; import/evidence commands now read "evidence-only … no automatic claim status change". |
| B2 | `cli.py` `update-claim` command | **Resolved** | Subcommand removed; CLI prints "claim review suggestions (manual update only)" / "no automatic claim status update performed". |
| B3 | `mcp/server.py` returns `claim_map.json` | **Resolved** | No `claim_map` reference in `src/aieng/mcp/server.py`. |
| B4 | `results/evidence_writer.py` writes claim-map | **Resolved** | No `claim_map` reference; module writes the evidence ledger only. |
| B5 | `validation/evidence_report_writer.py` requires claim-map | **Resolved** | Now: "we emit zeroed values without inspecting any claim_map." |
| B6 | `docs/command_reference.md` tracks claims | **Resolved** | Claim-tracking wording removed. |
| B7 | `docs/architecture.md` describes claim-state mutation | **Resolved** | Reframed: "Claim status review: claim status changes require human review with traceable evidence IDs." |
| B8 | `docs/agi_handoff_walkthrough.md` teaches `update-claim` | **Resolved** | `update-claim` workflow removed. |
| B9 | `docs/mvp_checkpoint.md` frames claim-map as release contract | **Reframed (acceptable)** | Now: "claim proposals are review artifacts requiring human review; no longer automatically generated." |
| B10 | `docs/reference_notation.md` embeds claim-map terms | **Resolved** | Claim-map notation removed. |
| W11 | `README.md` "certify engineering validity" | **Resolved** | No "certify" in `aieng/README.md`. |
| W12 | `README.md` "correctness stayed at ceiling" | **Resolved** | Now: "benchmark answer correctness (under the task rubric) stayed at ceiling". |
| W13 | `docs/benchmark_design.md` "geometric correctness" | **Fixed in this pass** | Changed to "geometric correspondence". |
| W14 | `status_writer.py` "not fully certified" | **Resolved** | Phrase removed. |
| W15 | `tests/test_assembly_graph.py` "validated without analysis" | **Not a defect** | Phrase sits inside a `claim_policy.forbidden:` list — it *demonstrates* the boundary (this claim is forbidden), it does not assert validation. Left as-is. |

### Extended scope — active `aieng-ui/` alpha surfaces (new this re-run)

The 2026 baseline scanned only the `aieng/` core library. The surfaces an external
agent actually reads in the alpha are in `aieng-ui/`; these were scanned now and are
**clean**:

- **MCP tool-schema descriptions** (`aieng-ui/backend/app/runtime_tool_schemas.py` `TOOL_SCHEMAS`, plus `runtime_registry/*.py`): no affirmative certification or auto-claim wording. The only "certification" hit is `runtime_registry/opt.py` "does **NOT** claim production certification" (correctly negated).
- **Frontend** (`aieng-ui/frontend/src`): `design_certified` is hardcoded `False` in `copilot_loop.py` and asserted `is False` in `test_api.py` — a one-way honesty flag, not a settable certification. An i18n honesty banner ("Not an engineering certification, claims not auto-advanced") is present.
- **`aieng-ui/` READMEs + docs**: consistently caveated ("does **not** certify design safety", forbidden-certification-language smoke checks in demo walkthroughs).

### Regression guard added

`aieng-ui/backend/tests/test_release_semantic_surfaces.py` pins this cleaned state:
it scans the static alpha-facing surfaces (top-level + package READMEs, `AGENTS.md`,
`CLAUDE.md`, `MCP_SETUP.md`) and the canonical MCP tool-schema descriptions for
affirmative prohibited certification / claim-advancement phrasing. Negated honesty
wording is intentionally not matched. This complements the runtime guards in
`app/project_health.py` and the export smoke checks (which cover *generated*
artifacts, not shipped text).

### Re-run conclusion

For `v0.1.0-alpha`, the **static semantic surfaces are now release-clean**. The
baseline's dominant blocker (claim-map / `update-claim` exposure across CLI, MCP,
docs) has been removed or reframed to evidence-only / human-review language, and the
posture is now pinned by an automated guard test.

---

## Findings (baseline — 2026; superseded by the re-run status above)

| Severity | File | Line | Problematic text | Why it is risky | Recommended replacement |
|---|---|---:|---|---|---|
| blocker | `src/aieng/cli.py` | 470 | `Write results/evidence_index.json and results/claim_map.json to an existing .aieng package` | Directly exposes claim-map creation in the CLI, which conflicts with the alpha invariant and the current release checklist (`No claim maps`). | Remove from alpha surface, or replace with evidence-only wording such as `Write results/evidence_index.json to record imported evidence references without changing claim state.` |
| blocker | `src/aieng/cli.py` | 634-635 | `update-claim` / `Update claim verification status and actual evidence IDs in results/claim_map.json` | Introduces an explicit claim-state mutation workflow that the alpha release is trying not to promise. | Remove from alpha surface, or defer to a future explicit acceptance workflow not included in `v0.1.0-alpha.1`. |
| blocker | `src/aieng/mcp/server.py` | 216-217 | `Return results/claim_map.json` | Exposes claim-map semantics as an agent-facing runtime capability, which conflicts with the claim-safety posture for alpha. | Remove from the alpha MCP surface, or replace with evidence/readiness/audit accessors only. |
| blocker | `src/aieng/results/evidence_writer.py` | 47 | `Write results/evidence_index.json and results/claim_map.json to an existing .aieng package.` | Treats claim-map writeback as normal package behavior rather than deferred future work. | Narrow to evidence ledger writing only, or mark the entire module experimental and out of alpha scope. |
| blocker | `src/aieng/validation/evidence_report_writer.py` | 50 | `evidence report requires validation/status.yaml, results/claim_map.json, and ...` | Makes claim-map presence look authoritative and required for review, which conflicts with the current no-claim-map release posture. | Base review reports on evidence, audit events, proposals, and readiness instead of claim maps. |
| blocker | `docs/command_reference.md` | 1030 | `These structured resources record what evidence ... is present, what engineering claims are being tracked, and whether each claim is currently supported by evidence.` | Public docs present claim-map tracking as a normal documented workflow. | Replace with evidence/proposal/readiness wording; remove claim-map tracking from the alpha command reference. |
| blocker | `docs/architecture.md` | 24 | `Explicit claim status update: claim status changes require explicit update-claim action ...` | Architectural docs still describe claim-state mutation as part of the supported design. | Replace with `Claim acceptance/rejection is intentionally out of scope for this alpha release.` |
| blocker | `docs/agi_handoff_walkthrough.md` | 267-270 | `When evidence supports or contradicts a claim, update the claim map:` / `aieng update-claim ...` | Teaches evaluators a workflow the alpha release explicitly says is not included. | Replace with proposal + review-readiness language and note that acceptance stays external/manual. |
| blocker | `docs/mvp_checkpoint.md` | 174 | `results/claim_map.json — structured claim-evidence map recording which engineering claims are pass/fail/unsupported` | Makes claim maps sound like part of the release contract rather than a deferred/legacy design. | Reframe as historical/experimental material or remove from alpha-facing docs. |
| blocker | `docs/reference_notation.md` | 77 | `claim — entries in results/claim_map.json.` | Embeds claim-map terminology into the reference system itself, increasing the chance that reviewers see claim maps as part of the stable alpha model. | Limit release notation examples to artifacts, evidence, proposals, audit events, and freshness state. |
| warning | `README.md` | 29 | `... does not replace CAD/CAE execution or certify engineering validity.` | The sentence is directionally correct, but the word `certify` keeps certification language in the main README. | Prefer `... does not establish engineering validity or certification status.` |
| warning | `README.md` | 12 | `accuracy improved ... correctness stayed at ceiling` | In README context, `correctness` can be read as engineering correctness rather than benchmark answer scoring. | Clarify as `benchmark answer correctness under the task rubric` or `task-score correctness`. |
| warning | `docs/benchmark_design.md` | 44 | `evaluates geometric correctness against a reference STEP file.` | Can be read as a project-level correctness guarantee rather than benchmark comparison against a known reference geometry. | Prefer `evaluates geometric correspondence against a reference STEP file.` |
| warning | `src/aieng/validation/status_writer.py` | 348 | `Geometry validity is not fully certified.` | Negated certification language still frames the system in certification terms. | Prefer `Geometry fidelity has not been independently established.` or `Geometry parsing remains experimental and review-required.` |
| warning | `tests/test_assembly_graph.py` | 37 | `claim assembly is validated without analysis` | Even inside a fixture/test, this phrase can normalize unsupported validation wording. | Rephrase as `claim assembly is structurally supported` or `unsupported claim of assembly adequacy`. |

## Release-impact summary

### Blockers

1. **Legacy claim-map surface remains active** across CLI, runtime/MCP, validation helpers, docs, and tests.
2. **Alpha-facing docs are internally inconsistent**: `docs/release-v0.1-alpha-checklist.md` says `No claim maps`, while multiple other docs and commands still document them as normal behavior.

### Warnings to clean up

1. Benchmark `correctness` wording needs tighter framing so it is not read as engineering correctness.
2. Certification-adjacent wording should be replaced with plainer `review-required` or `not established` language.

## Conservative release conclusion (baseline)

> **Superseded — see the "Re-run status" section at the top.** At the time of the
> baseline scan, the semantic story was **not yet release-clean** and the
> claim-map/update-claim surface was the dominant blocker. The 2026-06-13 re-run
> against current `main` confirms that surface is now resolved/reframed and the
> static surfaces are release-clean for `v0.1.0-alpha`.
