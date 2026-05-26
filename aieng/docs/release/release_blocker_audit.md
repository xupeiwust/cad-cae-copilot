# Release blocker semantic audit

Scope scanned: `README.md`, `docs/`, `examples/`, `src/`, and `tests/`.

This report lists release-relevant wording or surfaces that conflict with the current alpha positioning:

- `.aieng` is an auditable CAD/CAE context package.
- It is not an engineering certification or automatic validation system.
- It should not expose claim-map or claim-advancement semantics in the `v0.1.0-alpha.1` story.

Notes:
- Plain package/schema validation text was **not** flagged unless it risks being read as engineering validation.
- The largest finding is not one sentence but a repeated legacy surface: `results/claim_map.json`, `update-claim`, and related read/write flows still appear across CLI, docs, MCP, and tests.

## Findings

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

## Conservative release conclusion

For `v0.1.0-alpha.1`, the semantic story is **not yet release-clean**. The claim-map/update-claim surface is the dominant blocker even though tests are green.
