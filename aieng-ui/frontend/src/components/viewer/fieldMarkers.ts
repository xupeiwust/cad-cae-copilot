import * as THREE from "three";

import type { SolverFieldDescriptor } from "../../types";
import { formatFieldValue, resultFieldLabel } from "./resultFields";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";
import { findFieldExtrema } from "./fieldExtrema";

// Peak (max) = red, min = blue — matches the thermal legend (high warm / low cool).
const MAX_COLOR = 0xef4444;
const MIN_COLOR = 0x3b82f6;

function coordsSpan(coords: [number, number, number][]): number {
  const box = new THREE.Box3();
  for (const c of coords) box.expandByPoint(new THREE.Vector3(c[0], c[1], c[2]));
  const size = new THREE.Vector3();
  box.getSize(size);
  return Math.max(size.length(), 1e-6);
}

function marker(center: THREE.Vector3, radius: number, color: number): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 16, 16),
    new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.9 }),
  );
  mesh.position.copy(center);
  mesh.renderOrder = 1001; // draw over the model so the peak is never hidden
  return mesh;
}

function markerLabel(text: string, color: string, scale = 1): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return new THREE.Sprite(new THREE.SpriteMaterial({ color: 0xffffff }));
  }
  const fontSize = 14;
  ctx.font = `bold ${fontSize}px system-ui, sans-serif`;
  const metrics = ctx.measureText(text);
  const padding = 8;
  canvas.width = Math.ceil(metrics.width + padding * 2);
  canvas.height = Math.ceil(fontSize * 1.4 + padding);

  // Redraw after resize.
  ctx.font = `bold ${fontSize}px system-ui, sans-serif`;
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.fillText(text, padding, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    opacity: 0.92,
  });
  const sprite = new THREE.Sprite(material);
  sprite.renderOrder = 1002;
  // Scale sprite so text is a few world units wide.
  const aspect = canvas.width / canvas.height;
  sprite.scale.set(0.25 * aspect * scale, 0.25 * scale, 1);
  return sprite;
}

/**
 * Build the peak/min marker overlay: a red sphere at the field's maximum node and
 * a blue sphere at its minimum, placed in display coordinates. Only real solver
 * fields (source "frd" with per-node values) get markers — synthetic descriptors
 * return an empty group (honest: don't mark a fabricated field).
 */
export function buildFieldMarkerGroup(
  descriptor: SolverFieldDescriptor | null,
  transform: DisplayTransform,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "field-markers";
  if (
    !descriptor ||
    descriptor.source !== "frd" ||
    !Array.isArray(descriptor.values) ||
    !Array.isArray(descriptor.node_coords) ||
    descriptor.values.length === 0
  ) {
    return group;
  }
  const { max, min } = findFieldExtrema(descriptor.values, descriptor.node_coords);
  if (!max) return group;

  const radius = coordsSpan(descriptor.node_coords) * 0.025;
  const toDisplay = (c: [number, number, number]) => modelToDisplayVec(c[0], c[1], c[2], transform);

  const fieldLabel = resultFieldLabel(descriptor.field_name);
  const unit = descriptor.unit ?? "";

  const maxPos = toDisplay(max.coord);
  group.add(marker(maxPos, radius, MAX_COLOR));
  const maxLabel = markerLabel(`${fieldLabel} max: ${formatFieldValue(max.value, unit)}`, "#fca5a5");
  maxLabel.position.copy(maxPos).add(new THREE.Vector3(0, radius * 2.5, 0));
  group.add(maxLabel);

  if (min && min.index !== max.index) {
    const minPos = toDisplay(min.coord);
    group.add(marker(minPos, radius, MIN_COLOR));
    const minLabel = markerLabel(`${fieldLabel} min: ${formatFieldValue(min.value, unit)}`, "#93c5fd");
    minLabel.position.copy(minPos).add(new THREE.Vector3(0, radius * 2.5, 0));
    group.add(minLabel);
  }
  return group;
}

export function disposeFieldMarkerGroup(group: THREE.Group): void {
  group.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material.dispose();
    }
    if (obj instanceof THREE.Sprite) {
      const material = obj.material;
      if (material.map) material.map.dispose();
      material.dispose();
    }
  });
}
