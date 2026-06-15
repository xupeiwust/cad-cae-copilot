// Locate the peak (max) and min nodes of a result field. Pure — used to place
// the 3D peak/min markers and to answer "where is the highest stress?".

export type FieldExtreme = { value: number; coord: [number, number, number]; index: number };
export type FieldExtrema = { max: FieldExtreme | null; min: FieldExtreme | null };

export function findFieldExtrema(
  values: number[] | null | undefined,
  coords: [number, number, number][] | null | undefined,
): FieldExtrema {
  if (!Array.isArray(values) || !Array.isArray(coords) || values.length === 0) {
    return { max: null, min: null };
  }
  const n = Math.min(values.length, coords.length);
  let maxI = -1;
  let minI = -1;
  for (let i = 0; i < n; i += 1) {
    const v = values[i];
    if (!Number.isFinite(v) || !coords[i]) continue;
    if (maxI < 0 || v > values[maxI]) maxI = i;
    if (minI < 0 || v < values[minI]) minI = i;
  }
  if (maxI < 0) return { max: null, min: null };
  return {
    max: { value: values[maxI], coord: coords[maxI], index: maxI },
    min: { value: values[minI], coord: coords[minI], index: minI },
  };
}
