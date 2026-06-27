# Workbench UI Comfort Benchmark

Status: product UX benchmark for the AIENG Workbench. This note supports issue
#427 and should guide changes to Mission Control, the CAD-to-CAE workflow lane,
trust/status badges, and the VS Code handoff surface.

## Product Goal

AIENG should feel like a calm engineering workbench, not a marketing page and
not a pile of debug panels. The first viewport should answer three questions:

- What evidence package am I looking at?
- What is missing or blocked?
- What is the next safe action?

Advanced details must remain reachable, but they should not dominate the first
read. The `.aieng` package is the visible evidence anchor; runtime/tool status
and approval gates stay separate from package evidence.

## Peer Takeaways

- [Dune 3D](https://github.com/dune3d/dune3d): borrow the lightweight command
  emphasis and direct modeling focus. Avoid rebuilding a full CAD surface inside
  AIENG; our first screen should guide the evidence workflow, not compete with
  a CAD kernel.
- [CAD Sketcher](https://github.com/hlorus/CAD_Sketcher): borrow progressive
  disclosure inside an expert host UI. Avoid hiding constraints or uncertainty;
  use compact status and only expand details when useful.
- [CQ-editor](https://github.com/CadQuery/CQ-editor): borrow the code/preview
  split mental model: authored intent on one side, visual feedback on the other.
  Avoid making the Workbench a code editor-first product; AIENG's primary object
  is the evidence package.
- [ParaView](https://github.com/Kitware/ParaView): borrow honest handling of
  complex scientific state. Avoid pretending simulation state is simple; group
  complexity into pipeline/status surfaces with clear provenance.

## AIENG Rules

- Keep the 3D viewer as the visual anchor. Inspector surfaces should float or
  rail themselves around it rather than shrinking it into a dashboard tile.
- Use at most one primary next action in Mission Control. Secondary actions are
  copy prompts or links to existing expert panels.
- Make status labels short and consistent: `ready`, `missing`, `blocked`,
  `unknown`; trust badges use nouns such as `Preflight`, `Computed metrics`,
  `Approval blocked`, `Claim not advanced`.
- Do not show long explanatory text inside badges. Put detail in tooltips,
  notes, or the report.
- Do not use success styling for solver completion alone. Solver evidence,
  result summaries, design-target comparison, and claim advancement are separate
  states.
- Keep panels stable: fixed min heights for repeated cards, no hover-driven
  layout shifts, no text overlap, no nested card piles.
- Prefer quiet contrast, compact spacing, and restrained accent colors. Avoid
  decorative hero sections, gradient ornaments, and large marketing copy inside
  the tool.

## Review Checklist

Use this checklist before shipping UX work:

- The first viewport answers current state, missing evidence, and next safe
  action without scanning unrelated panels.
- Empty and blocked states are specific and calm.
- Advanced panels remain reachable without crowding Mission Control.
- `.aieng` package evidence is visibly separate from live runtime state.
- Approval gates are visible and not bypassed by copy prompts.
- No UI copy implies certification, production readiness, or engineering
  validation unless claim evidence explicitly supports it.
- The inspector rail remains readable between 300px and 380px wide.
- The VS Code embed keeps the viewer usable and does not duplicate the full
  Workbench inspector.
