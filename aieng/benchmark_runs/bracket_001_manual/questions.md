# Benchmark Questions: Bracket 001

These are the benchmark questions for the manual bracket reference run.

Ask **all** questions below in **both** Condition A (raw STEP input) and Condition B (`.aieng` package input). Use the same wording in both sessions.

Source: [`benchmarks/questions.md`](../../benchmarks/questions.md). Reproduced here for convenience so the benchmark run is self-contained.

Do not allow external RAG, MCP tools, skills, plugins, CAD tools, solver calls, LLM fine-tuning, or specialized CAD/CAE training in either session.

---

## A. Part identity

1. What is this part?
2. What is the likely engineering role of this part?

---

## B. Geometry and features

1. What are the main engineering features?
2. Which object IDs represent candidate holes, plates, and unknown features?
3. Which features are candidates rather than confirmed truth?

---

## C. Constraints and protected regions

1. Which features should not be modified?
2. Why are they protected?
3. What operations are forbidden?

---

## D. Simulation intent

1. What material is assigned?
2. What boundary conditions are intended?
3. What loads are intended?
4. What stress or validation targets exist?

---

## E. Validation state

1. Has a mesh been generated?
2. Has a solver run?
3. Is there evidence that the design is safe?
4. Which claims are validated and which are not?

---

## F. Modification proposal

1. Propose a mass-reduction change while preserving protected interfaces.
2. What validation steps are required before accepting the patch?


---

## H. CAE import and mapping

1. What CAE deck entities were imported?
2. Which CAE target is fixed?
3. Which CAE target receives load?
4. Are CAE targets automatically mapped or user-provided?
5. Which feature/interface does `FIXED_HOLES` map to?
6. Which feature/interface does `LOAD_FACE` map to?
7. Does imported CAE setup prove a solver was run?

---

## Scoring guidance

Score each category (A through H) with the rubric in [`benchmarks/scoring_rubric.md`](../../benchmarks/scoring_rubric.md).

Use [`scoring_sheet.md`](scoring_sheet.md) to record scores and evidence for both conditions.
