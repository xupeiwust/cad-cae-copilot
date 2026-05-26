# Benchmark Questions — Sample Bracket CAD Understanding

**Track**: A — CAD Understanding  
**Scenario**: `sample_bracket_cad_understanding`

These questions are drawn from [../../questions.md](../../questions.md) Track A and
adapted for the sample bracket fixture. Ask all questions in the same session, to the
same AI, in the order shown. Ask identical questions in both Condition A and Condition B.

---

## Q1 — Feature inventory

What features or objects does this model contain? For each one, state:
- its name
- its type (or your best-guess type, if uncertain)
- whether the type is confirmed by the source or is an inference on your part

---

## Q2 — Mounting holes

Which objects in this model are mounting holes? Cite the evidence for your answer.
If you are uncertain about any identification, state that explicitly and explain why.

---

## Q3 — Available geometry

What geometric information is currently available about this model?
What geometric information is missing or could not be determined from the input?

---

## Q4 — Explicit missingness

What information about this model is explicitly recorded as missing, unsupported,
or uncertain? List each item with its source.

If there is no explicit missingness record in the input, say so.

---

## Q5 — FEM preprocessing readiness

A downstream engineer wants to perform finite element analysis on this model.
Based on the available information:

(a) What information is already present that would be useful for FEM preprocessing?  
(b) What information is missing that would need to be obtained from external sources?  
(c) List the external steps that would be needed before a solver could run.

---

## Excluded capabilities (confirm before asking)

During this benchmark session, the following are excluded:

- MCP tool calls
- RAG or retrieval augmentation
- Skills, plugins, or LLM fine-tuning
- External CAD tool calls
- External CAE tool calls (CalculiX, Abaqus, Gmsh, etc.)
- Solver execution or result generation
- LLM API calls beyond prompting with the designated input files
