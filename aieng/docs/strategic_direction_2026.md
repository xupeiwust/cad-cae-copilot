# Strategic Direction (2026) — synthesis of the deep-research findings

Status: **strategy synthesis**, not a product contract. This distills the
actionable strategic conclusions from the 12-dimension deep-research report
(`deepresearch_result/cad_copilot_direction.agent.final.md`) into a short,
decision-oriented document the team can steer by.

It is the **market/strategy layer** above the existing docs — it does not replace
them:
- [`public-positioning.md`](public-positioning.md) — outward `.aieng` value pitch.
- [`core_position.md`](core_position.md) — inward "adapt CAD/CAE data to AI" rationale.
- [`roadmap.md`](roadmap.md) / [`agent_guided_optimization_direction.md`](agent_guided_optimization_direction.md) — execution roadmaps.

Honesty posture is unchanged: advisory / CAE-backed evidence / approval-gated /
baseline-safe; never "optimal", "production-certified", "guaranteed".

---

## 1. The one-line strategic thesis

**Be the infrastructure layer for AI engineering agents — "the Stripe of
engineering" — not another CAD UI.** The durable value is the *MCP tool surface +
`.aieng` auditable data package + deterministic critique + CAD→CAE closed loop*,
consumed by any agent/IDE — not a front-end users open.

Why this matters now: as AI-native IDEs (Cursor at ~$2B ARR, Windsurf, etc.)
absorb domain capability via MCP plugins, a standalone "CAD tool" gets commoditized
from above. A standardized MCP server + portable data package is defensible where a
UI is not.

## 2. What the research validates (we are on the right line)

- **Code-generation path (build123d/OpenCASCADE) is the winning bet.** Academic
  share of code-gen Text-to-CAD rose ~20%→~70% (2024→2026); build123d Pass@1 ≈
  0.59. Our determinism / parametric-editability / verifiability advantages
  directly answer the failure modes of direct B-Rep/mesh generation.
- **Our four differentiators are the moat:** stable topology pointers,
  **deterministic critique**, approval-gated actions, CAD→CAE closed loop. The
  report calls deterministic critique the *most under-rated* feature and predicts
  it shifts from "nice-to-have" to **regulatory expectation** (FDA/NMPA/ASME want
  explicit performance-boundary + failure-mode statements for AI-assisted
  engineering). Honest limitation statements are a *trust asset*, not a weakness.
- **MCP-first is a 6–12 month window.** MCP: ~97M monthly SDK downloads, donated to
  the Linux Foundation, NIST-favored agent protocol; yet Autodesk is the *only*
  legacy CAD vendor with an official MCP server. Engineering-domain MCP is nearly
  empty space.

## 3. What the research adds that our docs didn't capture

### 3a. Success metrics = embedding depth, not vanity
Steer by **MCP server installs, `.aieng` packages created, third-party
agent/IDE integrations** — not GitHub stars or end-user counts. These measure how
deeply we are embedded in the "AI engineering agent infrastructure" niche.

### 3b. Community = "Linux-kernel mode", not "FreeCAD mode"
Small expert core (2–3 architects) owning the MCP server architecture + `.aieng`
spec; the bulk of contribution is external developers extending MCP tools
(industry-specific operations, solver adapters) and `.aieng` plugins. Avoid the
FreeCAD trap of head-on UX competition with commercial CAD. (FreeCAD funding
$500–8k/project couldn't sustain full-time dev; Ondsel shut down 2024.)

### 3c. Open-Core is the sustainable model; pre-stage the license
Core MCP server + base CAD/CAE tools stay MIT; enterprise features (team collab,
compliance audit, industry critique rule-packs, hosting) are commercial. GitLab
validates ~67% enterprise upgrade. **Action with legal lead time:** introduce a
**CLA now** to preserve the option to move to Open-Core/BSL later (the
MongoDB/Elastic/Redis lesson) — this is a project-owner decision, flagged here.

### 3d. Vertical + China dual market (owner-level strategy, not code)
Report's weighted scoring: **automotive (4.45/5)** then **consumer electronics
(4.30/5)**. China offers a structural dual opening (localization mandate + AI-native
demand; MIT license removes procurement/political friction). These are
go-to-market calls for the owner — recorded here, not turned into code issues.

## 4. Technical priorities the research flags (now tracked as issues)

| Priority | Item | Status in our repo |
|---|---|---|
| P0 | Topology-opt → editable CAD (AMRTO/PYTOCAD) | **#130** (evaluation spike) + Phase-4 Epic #99 (contour path) |
| P0/P1 | NAFEMS/ASME V&V verification suite | **#131** (starter suite) — extends `cae_verification.py` |
| (core) | Deterministic critique as first-class | done + extended (#103 wired critique into optimization constraint evidence) |
| (mid) | Multi-objective / topology-to-sizing | Phase 4 Epic #99, Phase 5 Epic #100 (issues filed) |
| (mid/long) | Assembly depth (real contact, bolt preload), GP surrogate, multimodal input | future — not yet issued; deferred behind the above |

## 5. Key risks → our mitigations
- **OpenCASCADE float-precision / build123d LLM-friendliness limits** → numeric
  guards for degenerate geometry now; evaluate an ECIP-style wrapper later.
- **Open-source sustainability** → Open-Core + CLA (3c).
- **Cloud-vendor strip-mining** → CLA pre-stages a BSL-style transition if needed.
- **Legacy-vendor / AI-IDE encroachment** → win the MCP window: make `.aieng` the
  default engineering data package in the MCP ecosystem (depth metrics in 3a).

## 6. Near-term focus (what this changes for us right now)
1. Keep executing the agent-guided optimization roadmap (Phases 2B/3/4/5 — issues
   filed) — it *is* the differentiated closed loop.
2. Land the two newly-filed P0/P1 technical bets: **#130 AMRTO evaluation**,
   **#131 V&V starter suite**.
3. Treat MCP-server polish + `.aieng` portability + third-party integration as
   first-class (the infrastructure thesis), above net-new front-end.
4. Owner decisions to make deliberately (not code): CLA adoption, Open-Core
   timing, vertical/China GTM, pricing.

> Provenance: synthesized from the archived deep-research report
> [`research/cad_copilot_direction_research_2026.md`](research/cad_copilot_direction_research_2026.md)
> (executive summary, §1 positioning, §3 technical directions, §7 roadmap/risks).
> Market/competitive citations live in that report; this doc carries the decisions.
