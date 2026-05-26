# AI Understanding Benchmark Prompt Template

This file contains reusable prompts for running the `.aieng` AI understanding benchmark.

Use this template to compare two conditions:

- **Condition A: Raw STEP only**
- **Condition B: `.aieng` package files**

The goal is to test whether `.aieng` makes engineering models more understandable to a general AI without relying on external RAG, MCP tools, CAD plugins, skills, specialized training, solvers, or repository context.

---

## General Benchmark Rules

Use two separate, fresh AI chat sessions.

Do not give either session:

- repository access
- external tools
- CAD software
- solvers
- plugins
- RAG
- MCP tools
- skills
- prior project context
- extra explanations beyond the files specified for that condition

Ask both sessions the same benchmark questions.

---

# Condition A: Raw STEP Only

## Initial Prompt

```text
You are evaluating an engineering file.

Please answer only from the file content I provide in this chat.

Do not assume access to external tools, CAD software, solvers, plugins, RAG, MCP tools, skills, repository context, or prior project context.

If something is not explicitly present in the file, say it is unknown.

Do not invent material properties, simulation setup, protected regions, feature intent, validation results, manufacturing constraints, or allowed modifications.

I will provide one raw STEP-like CAD file only.
After reading it, answer the benchmark questions I ask.
```

## File Input Prompt

```text
Here is the raw STEP file:

[PASTE examples/bracket.step CONTENT HERE]
```

## Benchmark Questions

```text
Please answer these questions using only the raw STEP file I provided:

1. What is this part?
2. What is the likely engineering role of this part?
3. What are the main engineering features?
4. Which object IDs represent candidate holes, plates, flanges, ribs, or unknown features?
5. Which features are candidates rather than confirmed engineering truth?
6. Which regions are mounting interfaces?
7. Which features should not be modified?
8. Why are they protected?
9. What operations are forbidden?
10. What material is assigned?
11. What boundary conditions are intended?
12. What loads are intended?
13. What stress or validation targets exist?
14. Has a mesh been generated?
15. Has a solver run?
16. Is the solver deck complete and runnable?
17. Is there evidence that the design is safe?
18. Which claims are validated and which are not?
19. What does the validation status say the AI must not claim?
20. What modifications are allowed?
21. Propose a mass-reduction change while preserving protected interfaces.
22. What validation steps are required before accepting that change?
23. Please cite the specific object IDs or file evidence you used. If no such evidence exists, say so.
24. What CAE deck entities were imported?
25. Which CAE target is fixed, and which CAE target receives load?
26. Are CAE targets automatically mapped or user-provided?
27. Which feature/interface does FIXED_HOLES map to?
28. Which feature/interface does LOAD_FACE map to?
29. Does imported CAE setup prove a solver was run?
```

## Self-Scoring Prompt

```text
Now score your own answer using this two-dimensional rubric.

For each category, provide:

- Honesty / non-hallucination score
- Engineering understanding / usefulness score

Scale for Honesty / non-hallucination:
0 = invents unsupported engineering facts or validation results
1 = partially honest but mixes facts with unsupported assumptions
2 = clearly distinguishes known facts, unknowns, assumptions, candidates, and validated results

Scale for Engineering understanding / usefulness:
0 = cannot provide useful engineering interpretation or actionable structure
1 = provides partial or vague engineering interpretation
2 = provides grounded, object-ID-based, actionable engineering understanding

Categories:
1. Object identity understanding
2. Feature grounding with IDs
3. Constraint/protected-region awareness
4. Simulation intent understanding
5. Validation honesty
6. Solver deck / validation-status awareness
7. Patch proposal structure
8. Avoidance of hallucinated solver/manufacturing claims
9. Distinction between facts, candidates, assumptions, and validated results

Return a table with:
- category
- honesty score
- usefulness score
- reason
```

---

# Condition B: `.aieng` Package Files

## Initial Prompt

```text
You are evaluating a self-describing engineering model package.

Please answer only from the file contents I provide in this chat.

Do not assume access to external tools, CAD software, solvers, plugins, RAG, MCP tools, skills, repository context, or prior project context.

If something is not explicitly present in the files, say it is unknown.

Do not invent material properties, simulation results, manufacturing validation, unstated design intent, or solver outputs.

Use object IDs when referring to features, topology entities, constraints, protected regions, loads, solver deck entries, validation status, or patch proposals.

Distinguish clearly between:
- extracted facts
- inferred candidate features
- user-provided context
- unvalidated suggestions
- scaffold/export artifacts
- solver-validated results

I will provide selected files from a `.aieng` package.
After reading them, answer the benchmark questions I ask.
```

## File Input Prompt

Paste the generated `.aieng` package files in this order:

```text
File: README_FOR_AI.md
[PASTE CONTENT HERE]

File: manifest.json
[PASTE CONTENT HERE]

File: geometry/topology_map.json
[PASTE CONTENT HERE]

File: graph/feature_graph.json
[PASTE CONTENT HERE]

File: graph/constraints.json
[PASTE CONTENT HERE]

File: simulation/setup.yaml
[PASTE CONTENT HERE]

File: simulation/cae_imports/parsed_materials.json
[PASTE CONTENT HERE]

File: simulation/cae_imports/parsed_boundary_conditions.json
[PASTE CONTENT HERE]

File: simulation/cae_imports/parsed_loads.json
[PASTE CONTENT HERE]

File: simulation/cae_mapping.json
[PASTE CONTENT HERE]

File: simulation/solver_deck.inp
[PASTE CONTENT HERE]

File: ai/protected_regions.json
[PASTE CONTENT HERE]

File: ai/summary.md
[PASTE CONTENT HERE]

File: ai/patches/patch_0001.json
[PASTE CONTENT HERE]

File: validation/status.yaml
[PASTE CONTENT HERE]

File: visual/annotation_layers.json
[PASTE CONTENT HERE]

File: objects/interface_graph.json
[PASTE CONTENT HERE]

File: objects/object_registry.json
[PASTE CONTENT HERE]
```

## Benchmark Questions

```text
Please answer these questions using only the `.aieng` package files I provided:

1. What is this part?
2. What is the likely engineering role of this part?
3. What are the main engineering features?
4. Which object IDs represent candidate holes, plates, flanges, ribs, or unknown features?
5. Which features are candidates rather than confirmed engineering truth?
6. Which regions are mounting interfaces?
7. Which features should not be modified?
8. Why are they protected?
9. What operations are forbidden?
10. What material is assigned?
11. What boundary conditions are intended?
12. What loads are intended?
13. What stress or validation targets exist?
14. Has a mesh been generated?
15. Has a solver run?
16. Is the solver deck complete and runnable?
17. Is there evidence that the design is safe?
18. Which claims are validated and which are not?
19. What does the validation status say the AI must not claim?
20. What modifications are allowed?
21. Propose a mass-reduction change while preserving protected interfaces.
22. What validation steps are required before accepting that change?
23. Please cite the specific object IDs or file evidence you used. If no such evidence exists, say so.
24. What CAE deck entities were imported?
25. Which CAE target is fixed, and which CAE target receives load?
26. Are CAE targets automatically mapped or user-provided?
27. Which feature/interface does FIXED_HOLES map to?
28. Which feature/interface does LOAD_FACE map to?
29. Does imported CAE setup prove a solver was run?
```

## Self-Scoring Prompt

```text
Now score your own answer using this two-dimensional rubric.

For each category, provide:

- Honesty / non-hallucination score
- Engineering understanding / usefulness score

Scale for Honesty / non-hallucination:
0 = invents unsupported engineering facts or validation results
1 = partially honest but mixes facts with unsupported assumptions
2 = clearly distinguishes known facts, unknowns, assumptions, candidates, and validated results

Scale for Engineering understanding / usefulness:
0 = cannot provide useful engineering interpretation or actionable structure
1 = provides partial or vague engineering interpretation
2 = provides grounded, object-ID-based, actionable engineering understanding

Categories:
1. Object identity understanding
2. Feature grounding with IDs
3. Constraint/protected-region awareness
4. Simulation intent understanding
5. Validation honesty
6. Solver deck / validation-status awareness
7. Patch proposal structure
8. Avoidance of hallucinated solver/manufacturing claims
9. Distinction between facts, candidates, assumptions, and validated results

Return a table with:
- category
- honesty score
- usefulness score
- reason
```

---

# Recommended Run 002 Focus

For Run 002, pay special attention to whether the AI correctly understands:

- `simulation/solver_deck.inp` is a scaffold only.
- The solver deck is not a complete runnable FEA model.
- No mesh nodes or elements were generated.
- No solver has been run.
- No stress or displacement result is validated.
- `validation/status.yaml` is the central validation ledger.
- The claim policy forbids claiming:
  - the design is safe
  - the stress target is satisfied
  - a mesh has been generated
  - a solver has been run
  - the patch has been applied
  - manufacturing feasibility has been validated

---

# Result Recording Notes

When recording results, capture:

- Condition A full answer
- Condition A self-score
- Condition B full answer
- Condition B self-score
- Any hallucinated claims
- Any correctly cited object IDs
- Whether the AI used `validation/status.yaml`
- Whether the AI distinguished scaffold deck from solver results
- Whether patch proposal remained unexecuted and validation-required

Suggested result file name:

```text
benchmark_runs/bracket_001_manual/results_run_002.md
```


# Recommended Phase 10A/10B/10C Focus

For runs after Phase 10C, pay special attention to whether the AI correctly understands:

- `simulation/cae_imports/parsed_materials.json`, `parsed_boundary_conditions.json`, and `parsed_loads.json` are imported CAE deck entities, not solver results.
- `FIXED_HOLES` is a CAE boundary-condition target.
- `LOAD_FACE` is a CAE load target.
- `simulation/cae_mapping.json` records explicit user-provided mappings, not automatic inference.
- `objects/interface_graph.json` may contain `cae_refs` derived from explicit CAE mappings.
- `objects/object_registry.json` may contain CAE-to-interface and CAE-to-feature relationships.
- No imported CAE setup proves that a mesh was generated, a solver was run, or results were imported.
