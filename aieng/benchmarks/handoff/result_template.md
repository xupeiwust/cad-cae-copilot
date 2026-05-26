# Handoff Benchmark Result Template

Copy this template to `benchmarks/handoff/results/run_YYYYMMDDTHHMMSSZ.md` and fill it in after completing a benchmark run.

---

## Run metadata

| Field | Value |
|-------|-------|
| run_id | `run_YYYYMMDDTHHMMSSZ` |
| timestamp_utc | `YYYYMMDDTHHMMSSZ` |
| benchmark_scenario | `agent_handoff_v1` |
| question_set_path | `benchmarks/handoff/questions.md` |
| rubric_path | `benchmarks/handoff/scoring_rubric.md` |
| expected_observations_path | `benchmarks/handoff/expected_observations.md` |
| input_index_path | `benchmarks/handoff/input_index.md` |
| evaluator | (name or team) |
| provider | (e.g. Anthropic, OpenAI, Google) |
| model | (e.g. claude-sonnet-4-6, gpt-4o) |
| package_used | (path to `.aieng` package used) |

---

## Excluded capabilities (confirm all were excluded)

- [ ] MCP tool calls
- [ ] RAG or retrieval augmentation
- [ ] Skills, plugins, or LLM fine-tuning
- [ ] External CAD tool calls
- [ ] External CAE tool calls
- [ ] Solver execution
- [ ] Mesh generation
- [ ] Manufacturing checker calls
- [ ] LLM API calls beyond prompting with package contents

---

## Input files provided

List each file from the package that was provided to the AI:

- [ ] `task/task_spec.yaml`
- [ ] `task/external_tool_requirements.json`
- [ ] `results/evidence_index.json`
- [ ] `results/claim_map.json`
- [ ] `manifest.json`
- [ ] `README_FOR_AI.md`
- [ ] `ai/summary.md`
- [ ] `ai/protected_regions.json`
- [ ] `graph/feature_graph.json`
- [ ] `graph/constraints.json`
- [ ] `graph/aag.json`
- [ ] `objects/interface_graph.json`
- [ ] `simulation/setup.yaml`
- [ ] `validation/status.yaml`
- Other (list):

---

## Category scores

| Category | Name | Score (0/1/2) | Notes |
|----------|------|:---:|-------|
| 1 | Task understanding | | |
| 2 | CAD/CAE execution boundary | | |
| 3 | Protected-region / interface awareness | | |
| 4 | Evidence ledger understanding | | |
| 5 | Claim-map honesty | | |
| 6 | External tool handoff plan usefulness | | |
| 7 | Provenance and writeback awareness | | |
| 8 | Unsupported-claim refusal | | |
| **Total** | | **/16** | |

---

## Per-question notes

### A. Task intent

**A1** (task resource citation):
> *(agent answer summary)*

Score contribution to Category 1: [ ]

---

**A2** (execution mode):
> *(agent answer summary)*

Score contribution to Category 1: [ ]

---

**A3** (forbidden claims):
> *(agent answer summary)*

Score contribution to Category 1: [ ]

---

**A4** (evidence required before acceptance):
> *(agent answer summary)*

Score contribution to Category 1: [ ]

---

### B. Execution boundary

**B1** (what `.aieng` is responsible for):
> *(agent answer summary)*

Score contribution to Category 2: [ ]

---

**B2** (external capabilities required):
> *(agent answer summary)*

Score contribution to Category 2: [ ]

---

**B3** (forbidden core actions):
> *(agent answer summary)*

Score contribution to Category 2: [ ]

---

**B4** (`aieng_core_executes_external_tools`):
> *(agent answer summary)*

Score contribution to Category 2: [ ]

---

**B5** (package positioning):
> *(agent answer summary)*

Score contribution to Category 2: [ ]

---

### C. Protected regions and interfaces

**C1** (protected features):
> *(agent answer summary)*

**C2** (forbidden operations):
> *(agent answer summary)*

**C3** (fixed support interface):
> *(agent answer summary)*

**C4** (load application interface):
> *(agent answer summary)*

**C5** (geometry change on protected feature):
> *(agent answer summary)*

Score contribution to Category 3: [ ]

---

### D. Evidence ledger

**D1** (evidence items present):
> *(agent answer summary)*

**D2** (aieng_core vs external evidence):
> *(agent answer summary)*

**D3** (solver result evidence):
> *(agent answer summary)*

**D4** (mesh evidence):
> *(agent answer summary)*

**D5** (geometry modification evidence):
> *(agent answer summary)*

Score contribution to Category 4: [ ]

---

### E. Claim-evidence map

**E1** (all claim IDs and statuses):
> *(agent answer summary)*

**E2** (passing claims):
> *(agent answer summary)*

**E3** (unsupported claims — `unsupported` ≠ false):
> *(agent answer summary)*

**E4** (can agent assert solver-validated design?):
> *(agent answer summary)*

**E5** (what changes a solver claim from unsupported to pass?):
> *(agent answer summary)*

Score contribution to Category 5: [ ]

---

### F. Handoff plan

**F1** (bounded handoff plan):
> *(agent answer summary or verbatim excerpt)*

**F2** (candidate tools and status):
> *(agent answer summary)*

**F3** (writeback after geometry modification):
> *(agent answer summary)*

**F4** (writeback after solver run):
> *(agent answer summary)*

Score contribution to Category 6: [ ]

---

### G. Provenance and writeback

**G1** (`record_artifacts`):
> *(agent answer summary)*

**G2** (`record_tool_trace`):
> *(agent answer summary)*

**G3** (update evidence index after mesh):
> *(agent answer summary)*

**G4** (claim map update after solver):
> *(agent answer summary)*

**G5** (who updates evidence resources):
> *(agent answer summary)*

Score contribution to Category 7: [ ]

---

### H. Unsupported-claim refusal

**H1** (stress target claim):
> *(agent answer summary)*

**H2** (structural safety question):
> *(agent answer summary)*

**H3** (mesh generation question):
> *(agent answer summary)*

**H4** (solver run question):
> *(agent answer summary)*

**H5** (`unsupported` vs `fail` distinction):
> *(agent answer summary)*

Score contribution to Category 8: [ ]

---

### I. Package positioning

**I1** (`.aieng` positioning):
> *(agent answer summary)*

**I2** (MCP as optional interface):
> *(agent answer summary)*

**I3** (MCP cannot run solver/mesh/CAD):
> *(agent answer summary)*

---

### J. Integrity and limits

**J1** (solver-validated evidence present?):
> *(agent answer summary)*

**J2** (manufacturing certification present?):
> *(agent answer summary)*

**J3** (most important next external action):
> *(agent answer summary)*

---

## Summary observations

*(Brief evaluation summary — what the agent got right, what it missed, and which categories most benefited from Phase 14C resources)*

---

## Raw response

*(Paste the full agent response here, or link to a file)*

---

## Evaluator notes

*(Any additional notes, anomalies, or follow-up questions)*
