import * as THREE from "three";

import type { BrepFaceEntity } from "../../appTypes";
import { modelToDisplayVec, type DisplayTransform } from "./coordinateFrames";

// Face-highlight overlay generation: build translucent meshes that sit on top of
// the displayed geometry to mark selected B-Rep faces, plus the disposal helper.

export function disposeHighlightObject(child: THREE.Object3D) {
  if (child instanceof THREE.Mesh) {
    child.geometry.dispose();
    if (Array.isArray(child.material)) {
      for (const material of child.material) material.dispose();
    } else {
      child.material.dispose();
    }
  }
}

export function makeHighlightMaterial(): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    color: 0xfacc15,
    transparent: true,
    opacity: 0.62,
    depthTest: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -6,
    polygonOffsetUnits: -6,
  });
}

// Overlay built from a tessellated primitive's *own* geometry — exact for any
// face shape (planar or curved), unlike the bbox-centroid heuristic. Geometry
// is cloned so disposeHighlightObject can free it without touching the model.
export function createPrimitiveOverlay(prim: THREE.Mesh): THREE.Mesh {
  const mesh = new THREE.Mesh(prim.geometry.clone(), makeHighlightMaterial());
  prim.updateMatrixWorld(true);
  mesh.matrixAutoUpdate = false;
  mesh.matrix.copy(prim.matrixWorld);
  mesh.matrixWorldNeedsUpdate = true;
  mesh.renderOrder = 1000;
  return mesh;
}

export function createFaceHighlightMesh(object: THREE.Object3D, face: BrepFaceEntity, transform: DisplayTransform): THREE.Mesh | null {
  const bbox = face.bounding_box;
  if (!bbox || bbox.length !== 6) return null;
  // Map the model-frame face bbox/center/normal into the viewer frame so the
  // triangle-centroid test below runs in displayed coordinates.
  const cornerA = modelToDisplayVec(bbox[0], bbox[1], bbox[2], transform);
  const cornerB = modelToDisplayVec(bbox[3], bbox[4], bbox[5], transform);
  const min = new THREE.Vector3(Math.min(cornerA.x, cornerB.x), Math.min(cornerA.y, cornerB.y), Math.min(cornerA.z, cornerB.z));
  const max = new THREE.Vector3(Math.max(cornerA.x, cornerB.x), Math.max(cornerA.y, cornerB.y), Math.max(cornerA.z, cornerB.z));
  const size = new THREE.Vector3().subVectors(max, min);
  const diagonal = Math.max(size.length(), 1e-3);
  const pad = Math.max(diagonal * 0.015, 1e-4);
  const paddedMin = min.clone().subScalar(pad);
  const paddedMax = max.clone().addScalar(pad);
  const center = face.center && face.center.length === 3
    ? modelToDisplayVec(face.center[0], face.center[1], face.center[2], transform)
    : new THREE.Vector3().addVectors(min, max).multiplyScalar(0.5);
  const faceNormal = face.normal && face.normal.length === 3
    ? modelToDisplayVec(face.normal[0], face.normal[1], face.normal[2], transform).normalize()
    : null;
  const planarSurface = (face.surface_type ?? "").toLowerCase().includes("plane");
  const planeTolerance = Math.max(diagonal * 0.04, 0.15);
  const positions: number[] = [];
  const v0 = new THREE.Vector3();
  const v1 = new THREE.Vector3();
  const v2 = new THREE.Vector3();
  const centroid = new THREE.Vector3();
  const triangleNormal = new THREE.Vector3();
  const edge = new THREE.Vector3();

  object.updateMatrixWorld(true);
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const geo = node.geometry as THREE.BufferGeometry;
    const pos = geo.attributes.position;
    if (!pos) return;
    const index = geo.index;
    const triCount = index ? Math.floor(index.count / 3) : Math.floor(pos.count / 3);
    for (let tri = 0; tri < triCount; tri++) {
      const i0 = index ? index.getX(tri * 3) : tri * 3;
      const i1 = index ? index.getX(tri * 3 + 1) : tri * 3 + 1;
      const i2 = index ? index.getX(tri * 3 + 2) : tri * 3 + 2;
      v0.set(pos.getX(i0), pos.getY(i0), pos.getZ(i0)).applyMatrix4(node.matrixWorld);
      v1.set(pos.getX(i1), pos.getY(i1), pos.getZ(i1)).applyMatrix4(node.matrixWorld);
      v2.set(pos.getX(i2), pos.getY(i2), pos.getZ(i2)).applyMatrix4(node.matrixWorld);
      centroid.copy(v0).add(v1).add(v2).multiplyScalar(1 / 3);
      if (
        centroid.x < paddedMin.x || centroid.x > paddedMax.x ||
        centroid.y < paddedMin.y || centroid.y > paddedMax.y ||
        centroid.z < paddedMin.z || centroid.z > paddedMax.z
      ) {
        continue;
      }
      if (planarSurface && faceNormal) {
        triangleNormal.subVectors(v1, v0).cross(edge.subVectors(v2, v0)).normalize();
        const normalAligned = Math.abs(triangleNormal.dot(faceNormal)) > 0.72;
        const closeToPlane = Math.abs(centroid.clone().sub(center).dot(faceNormal)) <= planeTolerance;
        if (!normalAligned || !closeToPlane) continue;
      }
      const offset = faceNormal ? faceNormal.clone().multiplyScalar(Math.max(diagonal * 0.0025, 0.02)) : new THREE.Vector3();
      positions.push(
        v0.x + offset.x, v0.y + offset.y, v0.z + offset.z,
        v1.x + offset.x, v1.y + offset.y, v1.z + offset.z,
        v2.x + offset.x, v2.y + offset.y, v2.z + offset.z,
      );
    }
  });

  if (positions.length < 9) return null;
  const highlightGeometry = new THREE.BufferGeometry();
  highlightGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  highlightGeometry.computeVertexNormals();
  const mesh = new THREE.Mesh(highlightGeometry, makeHighlightMaterial());
  mesh.renderOrder = 1000;
  return mesh;
}
