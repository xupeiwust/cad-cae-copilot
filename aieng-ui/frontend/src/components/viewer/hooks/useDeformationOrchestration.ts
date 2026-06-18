import { useEffect, useState } from "react";
import * as THREE from "three";

import type { SolverFieldDescriptor } from "../../../types";
import { computeDeformationScale } from "../deformedShape";

/**
 * Own the deformed-shape overlay state for `ModelViewer`.
 *
 * Returns whether displacement vectors are available, the toggle state, the
 * exaggeration scale, and setters. The scale is auto-initialized from the
 * model bbox so that the maximum displacement is roughly 5 % of the diagonal.
 *
 * Also owns the animation playback state for #255 result animation /
 * modal mode-shape playback.
 */
export function useDeformationOrchestration(
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  objectRef: React.MutableRefObject<THREE.Object3D | null>,
  objectReadyKey: number,
) {
  const [showDeformedShape, setShowDeformedShape] = useState(false);
  const [deformationScale, setDeformationScale] = useState(1);
  const [animationActive, setAnimationActive] = useState(false);
  const [animationMode, setAnimationMode] = useState<"sweep" | "oscillate">("sweep");

  const deformationAvailable = Boolean(
    fieldDescriptor &&
      fieldDescriptor.source === "frd" &&
      Array.isArray(fieldDescriptor.vectors) &&
      fieldDescriptor.vectors.length > 0,
  );

  // Auto-init scale when a displacement field becomes active and geometry loads.
  useEffect(() => {
    const object = objectRef.current;
    if (!object || !fieldDescriptor?.vectors || fieldDescriptor.vectors.length === 0) {
      setShowDeformedShape(false);
      setAnimationActive(false);
      return;
    }
    const auto = computeDeformationScale(fieldDescriptor.vectors, object, 0.05);
    setDeformationScale(Number.isFinite(auto) && auto > 0 ? auto : 1);
  }, [fieldDescriptor?.field_name, fieldDescriptor?.project_id, fieldDescriptor?.load_case_id, fieldDescriptor?.vectors, objectReadyKey, objectRef]);

  return {
    deformationAvailable,
    showDeformedShape,
    setShowDeformedShape,
    deformationScale,
    setDeformationScale,
    animationActive,
    setAnimationActive,
    animationMode,
    setAnimationMode,
  };
}
