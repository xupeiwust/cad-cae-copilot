import * as THREE from "three";

import type { FieldRegionsDocument, FieldRegionCluster } from "../../types";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";

const STRESS_COLOR = 0xef4444;       // red-500
const DISPLACEMENT_COLOR = 0x3b82f6; // blue-500
const FALLBACK_COLOR = 0xfacc15;     // amber-300

function fieldNameToColorHint(field: string): number {
  const f = field.toLowerCase();
  if (f.includes("stress") || f.includes("von_mises") || f.includes("tresca")) return STRESS_COLOR;
  if (f.includes("displacement") || f.includes("disp")) return DISPLACEMENT_COLOR;
  return FALLBACK_COLOR;
}

function createClusterMarker(
  cluster: FieldRegionCluster,
  transform: DisplayTransform,
  scaleHint: number,
  maxMagnitude: number,
): THREE.Object3D {
  const group = new THREE.Group();
  group.name = `cluster-${cluster.id}`;
  const center = modelToDisplayVec(cluster.location.x, cluster.location.y, cluster.location.z, transform);

  const normalized = maxMagnitude > 0 ? cluster.magnitude.value / maxMagnitude : 0.5;
  const radius = scaleHint * (0.015 + normalized * 0.025);

  const color = fieldNameToColorHint("");
  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 16, 16),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.85,
      depthTest: false,
    }),
  );
  sphere.position.copy(center);
  sphere.renderOrder = 1100;
  group.add(sphere);

  // Small inner core for contrast.
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(radius * 0.4, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, depthTest: false }),
  );
  core.position.copy(center);
  core.renderOrder = 1101;
  group.add(core);

  // Label sprite with magnitude.
  const label = createLabelSprite(`${cluster.magnitude.value.toPrecision(3)} ${cluster.magnitude.unit}`, scaleHint * 0.04);
  label.position.copy(center).add(new THREE.Vector3(0, radius + scaleHint * 0.03, 0));
  group.add(label);

  (group as THREE.Object3D & { userData: Record<string, unknown> }).userData = {
    type: "field-region-cluster",
    cluster,
  };

  return group;
}

function createLabelSprite(text: string, scale: number): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    const material = new THREE.SpriteMaterial({ transparent: true, opacity: 0, depthTest: false });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(scale * 4, scale, 1);
    sprite.renderOrder = 1200;
    return sprite;
  }
  canvas.width = 256;
  canvas.height = 64;
  ctx.fillStyle = "rgba(2, 6, 23, 0.78)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#e2e8f0";
  ctx.font = "bold 24px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(scale * 4, scale, 1);
  sprite.renderOrder = 1200;
  return sprite;
}

function computeScaleHint(object: THREE.Object3D): number {
  const box = new THREE.Box3().setFromObject(object);
  const size = new THREE.Vector3().subVectors(box.max, box.min);
  const maxDim = Math.max(size.x, size.y, size.z);
  return Number.isFinite(maxDim) && maxDim > 0 ? maxDim : 1;
}

export function buildFieldRegionMarkerGroup(
  document: FieldRegionsDocument,
  object: THREE.Object3D,
  transform: DisplayTransform,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "field-region-markers";
  const scaleHint = computeScaleHint(object);
  const maxMagnitude = Math.max(
    1e-12,
    ...document.clusters.map((c) => c.magnitude.value),
  );
  for (const cluster of document.clusters) {
    group.add(createClusterMarker(cluster, transform, scaleHint, maxMagnitude));
  }
  return group;
}

export function disposeFieldRegionMarkerGroup(group: THREE.Group): void {
  group.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      const material = obj.material;
      if (Array.isArray(material)) material.forEach((m) => m.dispose());
      else material.dispose();
    } else if (obj instanceof THREE.Sprite) {
      obj.material.map?.dispose();
      obj.material.dispose();
    }
  });
}
