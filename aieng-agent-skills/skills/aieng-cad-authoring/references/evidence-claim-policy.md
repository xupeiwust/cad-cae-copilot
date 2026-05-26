# Evidence-claim policy

## The one rule

Evidence is not a claim. Successful execution is not engineering validation.

## What evidence in the package means

`results/evidence_index.json` records that a backend step ran and produced an artifact at a stable handle. It says "this step executed and emitted this output." It does not assert correctness, safety, manufacturability, tolerance acceptability, or simulation validity.

## Allowed agent statements

- "Backend X executed N steps; status: success / partial / failed."
- "A STEP file was written to `geometry/source.step`."
- "The modeling plan was schema-valid before execution."
- "Construction history confirms the intended primitives ran."
- "The planner recorded the following assumptions: …"
- "The diagnostic package contains the trace and evidence ledger for the failed step."

## Forbidden agent statements (on the basis of a successful package alone)

- "The design is valid."
- "The part will work."
- "The geometry is correct."
- "Dimensions are appropriate."
- "The part is manufacturable."
- "Stress / safety factor / weight is acceptable."
- "Simulation passed."

## claims_advanced

This skill never advances claims. Any execution result must leave `claims_advanced: false`. Claim proposals are review artifacts only and require human review.
