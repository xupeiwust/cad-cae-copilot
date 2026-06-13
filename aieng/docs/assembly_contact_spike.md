# Assembly CAE nonlinear contact modeling spike (#198)

Can the assembly CAE stack model a **minimal real nonlinear contact** case
(replacing the explicit `contact_physics_modeled:false` proxy) without
overstating production readiness? This spike answers from code inspection of the
assembly CAE v0 stack plus the CalculiX contact requirements.

> **Method note.** Code-analysis spike. No CalculiX contact solve was run (the
> `ccx` binary is not available in this environment; it ships in the Docker
> image). The honesty pins are exercised by `tests/test_assembly_contact_spike.py`.

## Verdict: **NO-GO for v0** — minimal real contact is not representable/runnable in the current stack

A real two-part contact case cannot be set up, solved, or reported with the v0
assembly CAE stack today. The gap is structural (no contact deck path, no real
surface extraction, no nonlinear step), not a tuning detail. The proxy path stays
honest (`contact_physics_modeled:false`, `contact_proxy` disabled) and a concrete
minimal-next-slice is recommended below for a dedicated follow-up.

## What a minimal real contact case requires (CalculiX)

For one planar two-block normal contact, a CalculiX deck needs:

1. **Solid meshes for both parts** (e.g. C3D8/C3D10) — not bounding boxes.
2. **Contact surfaces** — `*SURFACE, TYPE=ELEMENT` master/slave sets built from
   the *element faces* on each interface (not just an interface bbox).
3. **`*SURFACE INTERACTION`** + `*SURFACE BEHAVIOR` (e.g. hard or exponential
   pressure–overclosure); optional `*FRICTION` for tangential behavior.
4. **`*CONTACT PAIR`** (surface-to-surface or node-to-surface) tying the two surfaces.
5. **A nonlinear step** — `*STEP, NLGEOM` + `*STATIC` with contact convergence
   controls (increment/iteration limits), not a single linear `*STATIC, 1., 1.`.
6. **Contact result extraction** — `*CONTACT FILE`/`*CONTACT PRINT` (CDIS/CSTR) →
   parse contact pressure/penetration from the FRD/DAT.

## What the v0 stack provides (gap analysis)

| Requirement | v0 assembly stack | Gap |
|---|---|---|
| Per-part solid meshes | `mesh_ref` is an *optional external* per-part mesh; deck only `*INCLUDE`s them | not guaranteed; not validated as solids |
| Contact surfaces (element faces) | interface resolution gives **bbox / centroid / normal / area** (a geometry proxy) | **no element-face surface extraction** at interfaces |
| `*SURFACE INTERACTION` / `*CONTACT PAIR` | deck emits tie/spring **placeholders** only (`generate_assembly_solver_deck`) | **no contact-pair deck generation** |
| Nonlinear step | deck emits linear `*STATIC, 1., 1.` | **no `NLGEOM` / convergence controls** |
| Contact result extraction | result path normalizes generic/neutral metrics only | **no contact-pressure extraction** |
| `contact_proxy` handling | mapped to `unsupported_contact_proxy`, **disabled** (`unsupported_proxy_type`) | correct + honest, but means *no contact is attempted* |

`contact_physics_modeled` is hardcoded `false` across the model, deck diagnostics,
and result paths; `contact_proxy` connections are disabled for the solver and
listed under `_LIMITATIONS` ("Nonlinear/frictional contact is not modeled").

## Minimal contact-pair attempt → concrete blocker

Attempting one planar two-block contact in this environment is blocked by **all**
of:
- **(a)** no real per-part solid meshes available in the spike fixtures (and the
  v0 model does not require/validate them as solids);
- **(b)** no path to extract contact **element-face surfaces** at an interface —
  the resolver stops at an interface bbox/normal proxy (the #200 interface-NSET
  diagnostics are the closest foundation, but they too are geometry-coverage
  proxies, not meshed element faces);
- **(c)** no `*SURFACE INTERACTION` / `*CONTACT PAIR` / nonlinear-step deck
  generator;
- **(d)** `ccx` is not runnable in this spike environment (it ships in the Docker
  image, so a CI-only run would be the path);
- **(e)** no contact-result (pressure/penetration) extractor.

Any one of (a)–(c)/(e) is a from-scratch build; (d) means even a hand-written
deck could only be validated in CI/Docker. So the minimal case is **documented
as blocked**, not run.

## Honesty (preserved + test-covered)

- `contact_physics_modeled` stays **false** in `assembly_cae_model.json`
  (`solver_hints`), `assembly_solver_deck_generation.json` (`metadata`), and the
  result paths.
- `contact_proxy` is an `unsupported_contact_proxy`, disabled for the solver
  (`unsupported_proxy_type`) — covered by
  `test_contact_proxy_is_unsupported_and_not_solver_enabled` and, end-to-end for
  honesty flags, by `test_assembly_contact_spike.py`.
- No production-readiness or certification claim is made
  (`production_ready:false` throughout).

## Recommendation & minimal next slice (if pursued)

**Defer broad contact support to a dedicated implementation issue.** A credible
minimal slice, in order:

1. **Single planar two-block pair fixture** with real per-part solid meshes
   (small C3D8 blocks) checked into the test fixtures.
2. **Contact-surface extraction** — derive `*SURFACE, TYPE=ELEMENT` master/slave
   element-face sets at the interface, reusing the #200 interface-NSET foundation
   (extend it from node coverage to element faces).
3. **Contact deck generator** — emit `*SURFACE INTERACTION` + `*SURFACE BEHAVIOR`
   + `*CONTACT PAIR` + `*STEP, NLGEOM` + convergence controls, gated to the one
   supported pair; never fake it when prerequisites are absent.
4. **CI-only ccx run** (Docker image bundles `ccx`) + **contact-result extraction**
   (CDIS/CSTR → contact pressure).
5. **Flip `contact_physics_modeled` true ONLY** on a successful, non-error contact
   solve with extracted contact results — never from deck setup alone (mirror the
   #199 bolt-preload `modeled`-requires-evidence guard).

This is a multi-PR effort. Until then, the proxy path remains the honest default.

## Honesty / non-goals
- No general nonlinear-contact production support. No friction/contact-law breadth.
- Code-analysis spike only — no contact solve was run in this spike.
