# Benchmark Questions

Use the same questions for both input conditions:

- Condition A: raw STEP/B-rep/CAE-like input only.
- Condition B: generated `.aieng` package contents.

Do not allow external RAG, MCP tools, skills, plugins, CAD tools, solver calls, LLM fine-tuning, or specialized CAD/CAE training during the benchmark.

## A. Part identity

1. What is this part?
2. What is the likely engineering role of this part?

## B. Geometry and features

1. What are the main engineering features?
2. Which object IDs represent candidate holes, plates, and unknown features?
3. Which features are candidates rather than confirmed truth?

## C. Constraints and protected regions

1. Which features should not be modified?
2. Why are they protected?
3. What operations are forbidden?

## D. Simulation intent

1. What material is assigned?
2. What boundary conditions are intended?
3. What loads are intended?
4. What stress or validation targets exist?

## E. Validation state

1. Has a mesh been generated?
2. Has a solver run?
3. Is there evidence that the design is safe?
4. Which claims are validated and which are not?
5. Is the solver deck complete and runnable, or is it a scaffold only?
6. What does the validation status say the AI must not claim about this model?

## F. Modification proposal

1. Propose a mass-reduction change while preserving protected interfaces.
2. What validation steps are required before accepting the patch?

## G. Visual annotation

1. What does the visual annotation scaffold describe, and does it represent a rendered 3D view of the part?
2. Which features are assigned a `protected_region` visual role, and which are labeled `candidate_feature`?


## H. CAE import and mapping

1. What CAE deck entities were imported?
2. Which CAE target is fixed?
3. Which CAE target receives load?
4. Are CAE targets automatically mapped or user-provided?
5. Which feature/interface does `FIXED_HOLES` map to?
6. Which feature/interface does `LOAD_FACE` map to?
7. Does imported CAE setup prove a solver was run?

## I. Reference correctness (Phase 18C extension)

1. Quote canonical `@aieng[...]` references for key records you cite.
2. Which quoted references can be resolved from the package?
3. Which references are missing or malformed?

## J. Completeness and missingness reasoning (Phase 18C extension)

1. Which categories are `available` in completeness resources?
2. Which categories are `missing` or `partial`?
3. Which states are `unsupported`, and why is that not equivalent to `false`?

## K. Unsupported-claim correctness (Phase 18C extension)

1. Which claims are currently marked `unsupported`?
2. Which claims are `pass` or `fail` with attached evidence?
3. Does absence of evidence justify a fail conclusion?

## L. Evidence trace correctness (Phase 18C extension)

1. Which evidence IDs support which claims?
2. Which trace entries advanced which claims?
3. What producer/tool metadata exists for each evidence item?

## M. External-tool-boundary correctness (Phase 18C extension)

1. Which resources explicitly state that external tools execute CAD/CAE tasks?
2. Which actions remain outside `.aieng` core responsibility?
3. What validation steps are still required before accepting design safety claims?
