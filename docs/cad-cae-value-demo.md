# CAD->CAE Value Demo Runbook

This is the canonical reproducible value demo for issue #368. It turns one
small, editable CAD model into a real CalculiX solve, real FRD-derived viewer
fields, and a short engineering report.

The goal is not to make a new solver benchmark. The goal is to give every
external MCP agent the same clean, reviewable path through the current product:

```
natural language -> CAD -> face pointers -> CAE setup -> approved solver run -> real fields -> report
```

## Preconditions

- Workbench backend and viewer are running.
- Gmsh is importable in the backend environment.
- CalculiX is configured with a runnable command. On Windows use the conda form:

```powershell
$env:AIENG_CCX_CMD = "conda run -n calculix-env ccx"
```

- The connected agent has read `aieng.agent_readme`, `aieng.guide {topic: "cad"}`,
  and `aieng.guide {topic: "cae"}`.

If Gmsh or CalculiX is missing, stop and record the environment blocker. Do not
claim a successful demo.

## Canonical Packet

The fixed prompt sequence and single-solid CAD fixture live in:

```bash
python aieng-ui/backend/scripts/value_demo_packet.py --format markdown
```

Print only the build123d fixture code with:

```bash
python aieng-ui/backend/scripts/value_demo_packet.py --print-cad-code
```

After running the demo, perform a read-only evidence check on the resulting
package:

```bash
python aieng-ui/backend/scripts/value_demo_packet.py --check-package path/to/project.aieng
```

Use `--format json` for machine-readable output. A blocked result means the demo
is incomplete; do not treat synthetic fallback fields, empty FRD files, or
missing computed metrics as a successful #368 demo.

The fixture is intentionally a simple 100 x 20 x 10 mm single connected
cantilever beam. That shape matches the real-ccx integration test dimensions,
keeps topology selection easy, and avoids introducing assembly/contact failure
modes into the value demo.

## Agent Sequence

1. Create or select a project.

Use `aieng.create_project` with a human name such as `value-demo-cantilever` if
no suitable empty project exists.

2. Build the CAD model.

Call `cad.execute_build123d` with the canonical fixture code, `mode=replace`,
`model_kind=mechanical`, `response_detail=compact`, and `thumbnail=true`.

Required evidence:

- `geometry/generated.step`
- `geometry/topology_map.json`
- `graph/feature_graph.json`
- named part `value_demo_cantilever`

3. Pick face pointers.

Call `aieng.agent_context` and copy the end-face pointers:

- xmin end face -> `FIXED_END`
- xmax end face -> `LOAD_END`

The agent must use copied pointers from the current topology. Do not invent face
ids, and re-read `aieng.agent_context` after any topology-changing CAD edit.

4. Run the approved simulation pipeline.

Prefer the current one-call path:

```json
{
  "project_id": "<project_id>",
  "task_description": "Linear static Al6061-T6 cantilever: fixed support on the copied xmin end face, total 50 N downward load on the copied xmax end face.",
  "material_hint": "Al6061-T6",
  "mesh_size_mm": 6,
  "run_id": "value_demo_run_001",
  "load_case_id": "value_demo_load_case_001",
  "timeout_seconds": 300,
  "overwrite": true
}
```

Tool: `cae.run_simulation_pipeline`.

This tool is approval-gated. The demo recording must show that the workbench asks
for approval before the solver executes.

Fallback if the one-call pipeline is unavailable: run `cae.generate_mesh`,
`cae.generate_solver_input`, approval-gated `cae.run_solver`, and
`postprocess.refresh_cae_summary` in that order.

5. Verify the result is real.

The demo passes only if the package contains:

- `simulation/mesh/mesh.inp`
- `simulation/runs/value_demo_run_001/solver_input.inp`
- `simulation/runs/value_demo_run_001/solver_run.json`
- `simulation/runs/value_demo_run_001/outputs/result.frd`
- `results/computed_metrics.json`
- `results/result_summary.json`

Open the viewer field controls and show von Mises stress and displacement
magnitude. Synthetic fallback fields are a failed demo condition for this issue.

6. Generate the report.

Call `report.generate` or open:

```text
GET /api/projects/{project_id}/report
```

The short summary must cite:

- max displacement with unit and load case
- max von Mises stress with unit and load case
- safety factor when available
- the credibility tier or equivalent evidence statement
- limitations from the report/result summary

## Recording Checklist

- Create project and generate the single connected CAD model.
- Show the 4-view thumbnail or viewer model.
- Show copied fixed/load face pointers from the current topology.
- Show solver approval before execution.
- Show the viewer using real FRD-derived fields, not synthetic fallback.
- Show report output with cited metrics and limitations.

## Honesty Boundaries

- Linear static only.
- Mesh-dependent until a convergence study is run.
- CalculiX execution and FRD extraction are solver evidence, not certification.
- No physical validation, fatigue, buckling, nonlinear contact, or bolt preload
  is claimed.
- If any stage degrades to mocked, fixture-only, or synthetic data, mark the
  demo as incomplete rather than successful.

## Related Validation

The backend real-solver guard is:

```bash
pytest aieng-ui/backend/tests/test_cae_solve_integration.py -q
```

That test skips when Gmsh/build123d/CalculiX are unavailable; on a configured
machine it meshes and solves the same single-solid cantilever dimensions and
asserts positive FRD-derived displacement and von Mises metrics.
