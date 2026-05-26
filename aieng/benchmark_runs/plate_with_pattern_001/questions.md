# Questions (Coverage-Probe Extension)

Use the base benchmark questions from benchmarks/questions.md, then add the extension prompts below.

## I. Reference correctness

1. Quote the canonical reference for the base plate feature.
2. Quote the canonical reference for the protected hole pattern feature.
3. Which quoted references can be resolved from the provided files?

## J. Completeness and missingness reasoning

1. Which key categories are available in this package variant?
2. Which categories are missing?
3. Which categories are unsupported rather than false?

## K. Unsupported-claim correctness

1. Which claims are unsupported in results/claim_map.json (if present)?
2. Why must unsupported not be interpreted as failure?

## L. Evidence trace correctness

1. If evidence resources are present, which evidence IDs support which claims?
2. Is there any evidence proving a solver run?

## M. External-tool boundary correctness

1. Which resources indicate that external tools, not aieng core, execute CAD/CAE work?
2. What validations are still required before claiming design safety?
