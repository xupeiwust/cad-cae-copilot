# Canonical Engineering Scenarios

This catalog is the adoption-first scenario layer for AIENG. It turns the
existing backend demos, value-demo packet, and design-study regressions into
small scenario packs that contributors can run and review without guessing what
is real evidence.

Machine-readable source: [`canonical_engineering_scenarios.json`](canonical_engineering_scenarios.json).

## Policy

- Scenario metadata is catalog-only. It must not mutate CAD, run solvers, or
  change runtime behavior.
- Synthetic or fixture data may be useful for CI, but it must never be counted
  as real solver evidence.
- Real-tool scenarios must be skip-gated and clearly marked as operator-run.
- Every scenario needs entrypoints, verification commands, expected artifacts,
  and honesty boundaries before it graduates from a candidate to a full pack.

## Current Packs

| Scenario | Status | Lightweight check | Boundary |
|---|---|---|---|
| Cantilever CAD to CAE value demo | operator-runbook | `python -m pytest aieng-ui/backend/tests/test_value_demo_packet.py -q` | Real Gmsh/CalculiX required for the real demo; synthetic fields fail the demo. |
| Fixture plate with holes, fasteners, and material | cataloged gap | `python -m pytest aieng-ui/backend/tests/test_cad_generation.py aieng-ui/backend/tests/test_standards_bridge.py -q` | Standard-part semantics do not imply preload/contact physics. |
| Mass-reduction design target comparison | CI regression | `python -m pytest aieng-ui/backend/tests/test_design_study_demo.py -q` | Ranking is advisory; baseline geometry is not overwritten. [Pack](canonical-scenarios/design-study-demo.md) |
| Mesh diagnostics failure and recovery | cataloged gap | `python -m pytest aieng-ui/backend/tests/test_simulation_readiness.py aieng-ui/backend/tests/test_simulation_runner.py -q` | Preflight success is not solver success. |
| Sizing sweep with ranked candidates | CI regression | `python -m pytest aieng-ui/backend/tests/test_optimization_sizing_demo.py aieng-ui/backend/tests/test_iterative_optimization_demo.py -q` | Analytical or fixture metrics are not solver evidence. [Pack](canonical-scenarios/sizing-sweep-demo.md) |

## Graduation Checklist

A scenario is ready for a teammate to claim when it has:

- a stable ID and owner-facing title;
- one or more repo entrypoints;
- at least one lightweight verification command that can run in CI;
- optional real-tool checks marked `skip_gated`;
- expected `.aieng` package artifacts;
- explicit limitations and claim boundaries;
- a consumer surface such as README, MCP dogfood, Mission Control, or release demo.

The catalog intentionally includes both complete packs and cataloged gaps. This
lets us plan the demo surface without weakening the main CAD/CAE execution path.
