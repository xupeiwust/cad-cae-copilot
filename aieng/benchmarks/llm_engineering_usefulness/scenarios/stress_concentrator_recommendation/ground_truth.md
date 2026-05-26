# Ground truth — stress_concentrator_recommendation

## The setup

A steel bracket has been solved under a 6.5 kN lateral load. Yield strength
is 350 MPa; the load case declares a minimum required safety factor of 1.5
(i.e. max stress ≤ 233 MPa anywhere in the kept geometry).

Per-feature stress (`results/stress_by_feature.json`):

| Feature | Max stress | SF | Status |
|---|---|---|---|
| `back_wall` | 45 MPa | 7.78 | OK |
| `central_rib` | 140 MPa | 2.50 | OK |
| `flange` | 95 MPa | 3.68 | OK |
| **`fillet_inner_corner`** | **280 MPa** | **1.25** | **Below SF floor** |
| `fillet_outer_corner` | 78 MPa | 4.49 | OK |
| `mounting_hole` | 110 MPa | 3.18 | OK |
| `mounting_bosses` | 52 MPa | 6.73 | OK |

## The correct answer

**Identify `fillet_inner_corner` as the stress concentrator and recommend
increasing its radius.**

It is the only feature below the declared 1.5 SF floor (280 MPa vs the
233 MPa allowable). The geometry is a 1 mm fillet at the
`central_rib` / `flange` joint — classic stress-concentration territory.

A reasonable engineering response is to **increase the fillet radius** (e.g.
to 3–5 mm), which reduces the local concentration. The exact new radius is
out of scope for the prompt — a competent response proposes the action and
states that re-analysis is required to verify the new SF.

## What a correct answer must include

1. **The specific feature**: `fillet_inner_corner` (or "the 1 mm fillet",
   or "the inner-corner fillet at the rib-to-flange joint").
2. **A reasonable design response**: increase the fillet radius / round
   the corner more / use a larger fillet.
3. **Acknowledged uncertainty**: the recommendation requires re-analysis
   before being adopted. The model should NOT claim the fix is guaranteed.

A response that names the feature but proposes nothing is partial credit.
A response that proposes a fix without identifying the right feature is
partial credit. A response that names the wrong feature as the concentrator
is incorrect.

## Anti-hallucinations to watch for

- Claiming the recommendation **will** restore SF ≥ 1.5 (it might; FEA is
  required to confirm — the model has no way to know).
- Claiming the recommendation has been validated (it has not been).
- Recommending modification of `fillet_outer_corner` (5 mm, comfortable).
- Recommending removal of `central_rib` (carries load; SF 2.5).
- Inventing stress values not present in `stress_by_feature.json`.
- Claiming the part is safe as-is.
