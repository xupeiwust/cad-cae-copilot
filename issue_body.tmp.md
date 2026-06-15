### Auto min/max markers shipped (commit db70601)

The "where is the peak?" half is on main:
- **Peak/min 3D markers**: a red sphere at the field maximum node + a blue sphere at the minimum, placed from the descriptor's per-node `values` + `node_coords` (in display coordinates). Only real solver fields get markers; synthetic descriptors yield none.
- Pure `fieldExtrema.ts` (`findFieldExtrema`) + `fieldMarkers.ts` builder + `useFieldMarkerOverlay` hook (mirrors the assembly-check overlay pattern); a "Show peak/min" toggle in the viewer.
- The extrema **values** already read off the legend (#246); these add the 3D **location**.
- tsc clean; 185 vitest green (incl. new `fieldExtrema` tests); production build OK.

**Still open for this issue:** the interactive **click-to-probe** (raycast → nearest node → value tooltip). Deferred — it overlaps with the existing face-pick raycast and needs care to not conflict. Tracked here.
