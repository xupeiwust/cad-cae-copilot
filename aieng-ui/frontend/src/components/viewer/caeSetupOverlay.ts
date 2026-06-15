import * as THREE from "three";

import type { CaeSetupOverlayConstraint, CaeSetupOverlayFace, CaeSetupOverlayLoad, CaeSetupOverlayResponse } from "../../types";
import type { BrepFaceEntity, BrepGraphSnapshot } from "../../appTypes";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";
import { createFaceHighlightMesh, disposeHighlightObject } from "./highlights";

const LOAD_COLOR = 0xf87171;      // red-400
const CONSTRAINT_COLOR = 0x60a5fa; // blue-400
const STALE_COLOR = 0xfacc15;     // amber-300

function makeOverlayMaterial(color: number, opacity = 0.55): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthTest: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -4,
    polygonOffsetUnits: -4,
  });
}

function createColoredPrimitiveOverlay(prim: THREE.Mesh, color: number): THREE.Mesh {
  const mesh = new THREE.Mesh(prim.geometry.clone(), makeOverlayMaterial(color));
  prim.updateMatrixWorld(true);
  mesh.matrixAutoUpdate = false;
  mesh.matrix.copy(prim.matrixWorld);
  mesh.matrixWorldNeedsUpdate = true;
  mesh.renderOrder = 950;
  return mesh;
}

function createColoredFaceHighlightMesh(
  object: THREE.Object3D,
  face: BrepFaceEntity,
  transform: DisplayTransform,
  color: number,
): THREE.Mesh | null {
  const mesh = createFaceHighlightMesh(object, face, transform);
  if (!mesh) return null;
  mesh.material = makeOverlayMaterial(color);
  return mesh;
}

function modelVecToThree(arr: number[] | null | undefined): THREE.Vector3 | null {
  if (!arr || arr.length !== 3) return null;
  return new THREE.Vector3(arr[0], arr[1], arr[2]);
}

function displayCenter(face: CaeSetupOverlayFace, transform: DisplayTransform): THREE.Vector3 | null {
  const c = modelVecToThree(face.center_mm);
  if (!c) return null;
  return modelToDisplayVec(c.x, c.y, c.z, transform);
}

function displayDirection(dir: number[] | null | undefined, transform: DisplayTransform): THREE.Vector3 | null {
  const d = modelVecToThree(dir);
  if (!d) return null;
  return modelToDisplayVec(d.x, d.y, d.z, transform).normalize();
}

function displayNormal(face: CaeSetupOverlayFace, transform: DisplayTransform): THREE.Vector3 | null {
  return displayDirection(face.normal, transform);
}

function createLoadArrow(
  face: CaeSetupOverlayFace,
  load: CaeSetupOverlayLoad,
  transform: DisplayTransform,
  scaleHint: number,
): THREE.Object3D {
  const group = new THREE.Group();
  const origin = displayCenter(face, transform) ?? new THREE.Vector3();
  const dir = displayDirection(load.direction, transform);
  const magnitude = typeof load.value_n === "number" ? load.value_n : 0;
  const length = magnitude > 0 ? Math.min(Math.max(magnitude * scaleHint * 0.05, scaleHint * 0.04), scaleHint * 0.35) : scaleHint * 0.12;
  const headLength = Math.min(length * 0.25, scaleHint * 0.05);
  const headWidth = headLength * 0.6;

  if (dir && dir.length() > 0.001) {
    const arrow = new THREE.ArrowHelper(dir, origin, length, LOAD_COLOR, headLength, headWidth);
    arrow.renderOrder = 1100;
    group.add(arrow);
  }

  if (magnitude > 0) {
    const label = createLabelSprite(`${magnitude.toPrecision(3)} N`, scaleHint * 0.045);
    const tipOffset = dir ? dir.clone().multiplyScalar(length + headLength) : new THREE.Vector3(0, length, 0);
    label.position.copy(origin).add(tipOffset);
    group.add(label);
  }

  return group;
}

function createConstraintGlyph(
  face: CaeSetupOverlayFace,
  transform: DisplayTransform,
  scaleHint: number,
): THREE.Object3D {
  const group = new THREE.Group();
  const center = displayCenter(face, transform) ?? new THREE.Vector3();
  const normal = displayNormal(face, transform) ?? new THREE.Vector3(0, 1, 0);
  const size = scaleHint * 0.05;

  const geometry = new THREE.ConeGeometry(size * 0.4, size, 8);
  const material = new THREE.MeshBasicMaterial({ color: CONSTRAINT_COLOR, transparent: true, opacity: 0.85 });
  const cone = new THREE.Mesh(geometry, material);
  cone.renderOrder = 1100;

  // Orient cone so its axis aligns with -normal (glyph points into the fixed face).
  const target = center.clone().sub(normal);
  cone.position.copy(center);
  cone.lookAt(target);
  cone.rotateX(Math.PI / 2);
  group.add(cone);

  return group;
}

function createStaleMarker(center: THREE.Vector3, scaleHint: number): THREE.Object3D {
  const geometry = new THREE.SphereGeometry(scaleHint * 0.03, 8, 8);
  const material = new THREE.MeshBasicMaterial({ color: STALE_COLOR, transparent: true, opacity: 0.9 });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(center);
  mesh.renderOrder = 1100;
  return mesh;
}

function createLabelSprite(text: string, scale: number): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    // Graceful fallback for test environments without a 2D canvas context.
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
  ctx.font = "bold 28px sans-serif";
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

function brepFaceFromOverlay(face: CaeSetupOverlayFace): BrepFaceEntity | null {
  if (!face.face_id) return null;
  return {
    id: face.face_id,
    pointer: `@face:${face.face_id}`,
    kind: "face",
    center: face.center_mm ?? null,
    normal: face.normal ?? null,
    bounding_box: face.bounding_box_mm ?? null,
    surface_type: face.surface_type ?? null,
  } as BrepFaceEntity;
}

export function buildCaeSetupGroup(
  overlay: CaeSetupOverlayResponse,
  faceMeshes: Map<string, THREE.Mesh[]>,
  object: THREE.Object3D,
  brepSnapshot: BrepGraphSnapshot | null,
  transform: DisplayTransform,
): THREE.Group {
  const group = new THREE.Group();
  group.name = "cae-setup-overlay";
  const scaleHint = computeScaleHint(object);

  const seenFaces = new Set<string>();

  for (const load of overlay.loads ?? []) {
    for (const face of load.faces ?? []) {
      if (!face.face_id) continue;
      seenFaces.add(face.face_id);
      const color = face.stale ? STALE_COLOR : LOAD_COLOR;

      if (faceMeshes.size > 0) {
        for (const prim of faceMeshes.get(face.face_id) ?? []) {
          group.add(createColoredPrimitiveOverlay(prim, color));
        }
      } else {
        const bf = brepFaceFromOverlay(face);
        if (bf) {
          const mesh = createColoredFaceHighlightMesh(object, bf, transform, color);
          if (mesh) group.add(mesh);
        }
      }

      if (face.stale) {
        const center = displayCenter(face, transform);
        if (center) group.add(createStaleMarker(center, scaleHint));
      } else {
        group.add(createLoadArrow(face, load, transform, scaleHint));
      }
    }
  }

  for (const constraint of overlay.constraints ?? []) {
    for (const face of constraint.faces ?? []) {
      if (!face.face_id) continue;
      seenFaces.add(face.face_id);
      const color = face.stale ? STALE_COLOR : CONSTRAINT_COLOR;

      if (faceMeshes.size > 0) {
        for (const prim of faceMeshes.get(face.face_id) ?? []) {
          group.add(createColoredPrimitiveOverlay(prim, color));
        }
      } else {
        const bf = brepFaceFromOverlay(face);
        if (bf) {
          const mesh = createColoredFaceHighlightMesh(object, bf, transform, color);
          if (mesh) group.add(mesh);
        }
      }

      if (face.stale) {
        const center = displayCenter(face, transform);
        if (center) group.add(createStaleMarker(center, scaleHint));
      } else {
        group.add(createConstraintGlyph(face, transform, scaleHint));
      }
    }
  }

  return group;
}

export function disposeCaeSetupGroup(group: THREE.Group) {
  group.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      disposeHighlightObject(child);
    } else if (child instanceof THREE.Sprite) {
      child.material.map?.dispose();
      child.material.dispose();
    } else if (child instanceof THREE.ArrowHelper) {
      child.dispose();
    }
  });
}
