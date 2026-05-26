# Questions — Flange Coverage Probe (Phase 18C-min)

Use the base benchmark questions from `benchmarks/questions.md`, then add the
extension prompts below for Phase 18C-min scoring categories.

---

## Base questions (from benchmarks/questions.md)

Apply all base A–H question groups to both variants.

---

## I. Reference correctness

1. Quote the canonical reference for the flange body feature.
2. Quote the canonical reference for the bolt-hole mounting pattern.
3. Quote the canonical reference for the pipe bore feature.
4. Which quoted references can be resolved from the provided files?
5. What happens if a reference contains an ID that does not appear in the provided resources?

---

## J. Completeness and missingness reasoning

1. Which key categories are available in this package variant?
2. Which categories are missing from the sparse variant but present in the rich variant?
3. Is the absence of solver results in this package the same as solver failure?
4. How does the completeness report represent missing vs unsupported resources?

---

## K. Unsupported-claim correctness

1. Identify any claims in `results/claim_map.json` (if present) with `verification_status: unsupported`.
2. Why should `unsupported` not be interpreted as `fail` or `false`?
3. Would it be correct to say "the design is safe" based on the current package state?

---

## L. Evidence trace correctness

1. If evidence resources are present, which evidence IDs support which claims?
2. Which tool produced each evidence item, and what is its verification status?
3. Is there any evidence proving a solver run has been completed?
4. Is there any evidence proving that mesh generation has been completed?

---

## M. External-tool boundary correctness

1. Which resources indicate that external tools — not `.aieng` core — execute CAD/CAE work?
2. What is the role of `task/external_tool_requirements.json` if present?
3. What validations are still required before the bolt-hole pattern or pipe bore could be modified?
4. What would need to happen before the maximum von Mises stress constraint could be marked as verified?

---

## N. Dual-protected-interface awareness

1. How many interfaces are protected in this package? Which are they?
2. A proposal to reduce flange ring mass is suggested. What must it preserve?
3. If the pipe bore diameter is changed, which constraints are violated?
