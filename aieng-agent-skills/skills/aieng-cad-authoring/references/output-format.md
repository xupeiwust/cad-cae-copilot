# Final response format

Use this template. Keep each section short. If a section has no content, write "(none)" rather than omitting it.

## Template

**Summary**
One sentence: what was authored, which backend, success / partial / failed.

**Generated artifacts**

- Package path: `<path>.aieng`
- Geometry: `geometry/source.step` (present | absent | placeholder)
- Construction history: N steps executed
- Evidence entries: N

**Assumptions**
List every assumption from `modeling_plan.assumptions`. Mark assumptions with `requires_user_confirmation: true` clearly (for example with a leading `⚠`). Do not invent additional assumptions beyond what the plan records.

**Validation and evidence status**

- Plan validation: passed | failed (cite messages).
- Backend status: success | partial | failed.
- `claims_advanced: false` (always for this skill).
- Evidence is recorded; evidence is not a claim (see `evidence-claim-policy.md`).

**Limitations**

- No engineering validation performed.
- No simulation, manufacturability, material, or tolerance analysis.
- Phase 1 supports only `create_box` and `create_cylindrical_cut`.
- (Other limitations specific to this run.)

**Next recommended actions**

- Open the STEP in CAD to visually inspect (if geometry available).
- Review the assumptions list; correct any that are wrong by re-running with refined intent.
- (Other run-specific suggestions.)

## Categories to keep separate

- **Generated geometry** — artifacts the backend wrote (STEP files, construction history entries).
- **Assumptions** — what the planner guessed, defaulted, or inferred. Pulled from `modeling_plan.assumptions`.
- **Verified facts** — schema validity, backend exit status, presence or absence of expected files.
- **Unsupported claims** — anything the user might want said about strength, safety, accuracy, tolerance, manufacturability, simulation results. Mark these as not supported by this package.
- **Next steps** — concrete user actions, not interpretive judgments.
