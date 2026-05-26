# Raw STEP/B-rep Expected Limitations

This document records expected limitations when a general AI sees only raw STEP/B-rep/CAE-like text, without external augmentation.

## Expected limitations

### Difficulty mapping B-rep entities to engineering features

Raw STEP/B-rep data is typically organized for geometry kernels and exchange workflows, not for direct semantic interpretation by general intelligence. Even when geometric entities are present, their engineering meaning is often implicit. A general AI may struggle to determine which faces form a mounting hole, base plate, rib, flange, boss, or protected interface.

### Lack of design intent

Raw CAD exchange files generally do not explain why a feature exists, which design tradeoffs matter, which dimensions are critical, or which regions must remain stable. The AI may infer possible intent, but those inferences are not grounded in explicit source-of-truth context.

### Lack of protected regions

Raw geometry usually does not say which features should not be modified. A general AI may not know that mounting interfaces, hole patterns, datum faces, load interfaces, or assembly-critical regions are protected.

### Lack of simulation context

Raw STEP/B-rep input usually lacks material assignments, boundary conditions, loads, solver target, units for analysis intent, and validation targets. A general AI may need to guess or ask for external context.

### Lack of validation status

Raw geometry does not normally record whether a mesh was generated, whether a solver ran, whether stress/displacement results exist, or whether manufacturing checks passed. This increases the risk of hallucinated safety or manufacturability claims.

### Likely need for guessing or external tools

A general AI reading raw STEP/B-rep-like text may need to guess engineering meaning or call external tools to inspect geometry. That can be useful for execution, but it means the file itself did not carry enough semantics for basic understanding.

## Expected outcome

In the raw-input condition, good answers should be cautious. They should acknowledge missing design intent, protected regions, simulation setup, and validation evidence. Poor answers may overclaim feature meaning, safety, manufacturability, or solver results.
