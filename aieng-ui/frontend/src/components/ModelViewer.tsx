import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { api } from "../api";
import type { BrepGraphSnapshot, CadGenerationProgress, PickedFace, ViewerLoadState } from "../appTypes";
import { fieldLabel, resolveAssetFormat } from "../appUtils";
import type { SolverFieldDescriptor } from "../types";
import { CadProgressPanel } from "./CadProgressPanel";

function sampleColormap(t: number, name?: string | null): THREE.Color {
  const c = Math.max(0, Math.min(1, t));
  if (name === "coolwarm") {
    // blue(0) -> white(0.5) -> red(1)
    const r = c < 0.5 ? 0.2 + c * 1.6 : 1.0;
    const g = c < 0.5 ? 0.2 + c * 1.6 : 1.0 - (c - 0.5) * 2.0;
    const b = c < 0.5 ? 1.0 : 1.0 - (c - 0.5) * 1.6;
    return new THREE.Color(r, g, b);
  }
  // thermal: blue -> cyan -> green -> yellow -> red
  const r = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 3)));
  const g = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 2)));
  const b = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * c - 1)));
  return new THREE.Color(r, g, b);
}

function applyYNormalizedColors(object: THREE.Object3D, colormap?: string | null): boolean {
  let applied = false;
  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const geo = node.geometry as THREE.BufferGeometry;
    const pos = geo.attributes.position;
    if (!pos) return;
    let yMin = Infinity;
    let yMax = -Infinity;
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i);
      if (y < yMin) yMin = y;
      if (y > yMax) yMax = y;
    }
    const yRange = yMax > yMin ? yMax - yMin : 1;
    const colors = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      const col = sampleColormap((pos.getY(i) - yMin) / yRange, colormap);
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    node.material = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.1, roughness: 0.65 });
    applied = true;
  });
  return applied;
}

type UniformGrid = {
  cellSize: number;
  minX: number;
  minY: number;
  minZ: number;
  cells: Map<string, number[]>;
};

function buildUniformGrid(nodeCoords: [number, number, number][]): UniformGrid {
  if (nodeCoords.length === 0) {
    return { cellSize: 1, minX: 0, minY: 0, minZ: 0, cells: new Map() };
  }
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (const [x, y, z] of nodeCoords) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  }
  const dx = maxX - minX, dy = maxY - minY, dz = maxZ - minZ;
  const diagonal = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const cellSize = Math.max(diagonal / Math.sqrt(nodeCoords.length), 1e-6);

  const cells = new Map<string, number[]>();
  for (let i = 0; i < nodeCoords.length; i++) {
    const [x, y, z] = nodeCoords[i];
    const ix = Math.floor((x - minX) / cellSize);
    const iy = Math.floor((y - minY) / cellSize);
    const iz = Math.floor((z - minZ) / cellSize);
    const key = `${ix},${iy},${iz}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key)!.push(i);
  }
  return { cellSize, minX, minY, minZ, cells };
}

function nearestNodeIndex(
  vx: number,
  vy: number,
  vz: number,
  grid: UniformGrid,
  nodeCoords: [number, number, number][],
): number {
  const { cellSize, minX, minY, minZ, cells } = grid;
  const ix = Math.floor((vx - minX) / cellSize);
  const iy = Math.floor((vy - minY) / cellSize);
  const iz = Math.floor((vz - minZ) / cellSize);

  let bestIdx = -1;
  let bestDist = Infinity;
  let searchRadius = 1;

  while (searchRadius <= 3) {
    let foundAny = false;
    for (let dx = -searchRadius; dx <= searchRadius; dx++) {
      for (let dy = -searchRadius; dy <= searchRadius; dy++) {
        for (let dz = -searchRadius; dz <= searchRadius; dz++) {
          if (searchRadius > 1 && Math.abs(dx) < searchRadius && Math.abs(dy) < searchRadius && Math.abs(dz) < searchRadius) {
            continue;
          }
          const key = `${ix + dx},${iy + dy},${iz + dz}`;
          const indices = cells.get(key);
          if (!indices) continue;
          foundAny = true;
          for (const idx of indices) {
            const [nx, ny, nz] = nodeCoords[idx];
            const d = (vx - nx) ** 2 + (vy - ny) ** 2 + (vz - nz) ** 2;
            if (d < bestDist) {
              bestDist = d;
              bestIdx = idx;
            }
          }
        }
      }
    }
    if (bestIdx !== -1) break;
    if (!foundAny && searchRadius >= 3) break;
    searchRadius++;
  }

  if (bestIdx === -1) {
    for (let i = 0; i < nodeCoords.length; i++) {
      const [nx, ny, nz] = nodeCoords[i];
      const d = (vx - nx) ** 2 + (vy - ny) ** 2 + (vz - nz) ** 2;
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }
  }
  return bestIdx;
}

function checkBboxAlignment(
  nodeCoords: [number, number, number][],
  object: THREE.Object3D,
): { status: "aligned" | "suspicious"; reason?: string } {
  const meshBox = new THREE.Box3().setFromObject(object);
  if (meshBox.isEmpty()) return { status: "suspicious", reason: "Mesh bbox empty" };

  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (const [x, y, z] of nodeCoords) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  }

  const frdCenter = new THREE.Vector3((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2);
  const meshCenter = new THREE.Vector3();
  meshBox.getCenter(meshCenter);
  const frdSize = new THREE.Vector3(maxX - minX, maxY - minY, maxZ - minZ);
  const meshSize = new THREE.Vector3();
  meshBox.getSize(meshSize);

  const effectiveMeshSize = new THREE.Vector3(
    meshSize.x < 1e-6 ? 1 : meshSize.x,
    meshSize.y < 1e-6 ? 1 : meshSize.y,
    meshSize.z < 1e-6 ? 1 : meshSize.z,
  );

  const centerDist = frdCenter.distanceTo(meshCenter);
  const meshDiagonal = Math.sqrt(
    effectiveMeshSize.x ** 2 + effectiveMeshSize.y ** 2 + effectiveMeshSize.z ** 2,
  );
  if (meshDiagonal === 0) return { status: "suspicious", reason: "Mesh has zero size" };

  if (centerDist / meshDiagonal > 0.5) {
    return {
      status: "suspicious",
      reason: `Center offset ${(centerDist / meshDiagonal * 100).toFixed(1)}% of diagonal`,
    };
  }

  const sizeRatioX = frdSize.x / (meshSize.x || 1);
  const sizeRatioY = frdSize.y / (meshSize.y || 1);
  const sizeRatioZ = frdSize.z / (meshSize.z || 1);
  if (
    sizeRatioX < 0.01 || sizeRatioX > 100 ||
    sizeRatioY < 0.01 || sizeRatioY > 100 ||
    sizeRatioZ < 0.01 || sizeRatioZ > 100
  ) {
    return { status: "suspicious", reason: "Size ratio out of bounds" };
  }
  return { status: "aligned" };
}

function applyFieldColors(
  object: THREE.Object3D,
  values: number[],
  nodeCoords: [number, number, number][],
  minVal: number,
  maxVal: number,
  colormap?: string | null,
): { applied: boolean; bboxStatus: "aligned" | "suspicious" | null; warnings: string[] } {
  let applied = false;
  const warnings: string[] = [];
  const valueRange = maxVal > minVal ? maxVal - minVal : 1;

  const grid = buildUniformGrid(nodeCoords);
  const bboxCheck = checkBboxAlignment(nodeCoords, object);

  object.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    const geo = node.geometry as THREE.BufferGeometry;
    const pos = geo.attributes.position;
    if (!pos) return;
    const colors = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      const vx = pos.getX(i);
      const vy = pos.getY(i);
      const vz = pos.getZ(i);
      const bestIdx = nearestNodeIndex(vx, vy, vz, grid, nodeCoords);
      const val = values[bestIdx] ?? minVal;
      const t = (val - minVal) / valueRange;
      const col = sampleColormap(t, colormap);
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    node.material = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.1, roughness: 0.65 });
    applied = true;
  });
  if (bboxCheck.reason) warnings.push(bboxCheck.reason);
  return { applied, bboxStatus: bboxCheck.status, warnings };
}

function fitCameraToObject(
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update(): void },
  object: THREE.Object3D,
) {
  const bounds = new THREE.Box3().setFromObject(object);
  if (bounds.isEmpty()) return false;

  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z, 1);
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const distance = (maxDimension / (2 * Math.tan(fov / 2))) * 1.8;

  camera.near = Math.max(distance / 100, 0.1);
  camera.far = Math.max(distance * 20, 1000);
  camera.position.copy(center).add(new THREE.Vector3(distance, distance * 0.7, distance));
  camera.lookAt(center);
  camera.updateProjectionMatrix();

  controls.target.copy(center);
  controls.update();
  return true;
}

export function ModelViewer({
  assetUrl,
  assetFormat,
  fieldDescriptor,
  projectId,
  pickedFaces,
  onAddPickedFace,
  onClearPickedFaces,
  onInsertToChat,
  onRunPreprocess,
  cadGenerationProgress,
  highlightedFaceIds,
  brepSnapshot,
  onClearHighlightedFaces,
}: {
  assetUrl?: string | null;
  assetFormat?: string | null;
  fieldDescriptor?: SolverFieldDescriptor | null;
  projectId?: string | null;
  pickedFaces: PickedFace[];
  onAddPickedFace(face: PickedFace): void;
  onClearPickedFaces(): void;
  onInsertToChat(text: string): void;
  onRunPreprocess(prompt: string): Promise<void>;
  cadGenerationProgress: CadGenerationProgress | null;
  highlightedFaceIds: Set<string>;
  brepSnapshot: BrepGraphSnapshot | null;
  onClearHighlightedFaces(): void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  // Scene refs shared between the asset-loading effect and the highlight effect.
  const sceneRef = useRef<THREE.Scene | null>(null);
  const highlightGroupRef = useRef<THREE.Group | null>(null);
  const [viewerState, setViewerState] = useState<{ status: ViewerLoadState; detail: string }>({
    status: "idle",
    detail: "等待生成预览资产",
  });
  const [tooltipFace, setTooltipFace] = useState<PickedFace | null>(null);
  const [preprocessBusy, setPreprocessBusy] = useState(false);
  const fieldDescriptorKey = fieldDescriptor
    ? [
        fieldDescriptor.project_id,
        fieldDescriptor.field_name,
        fieldDescriptor.format,
        fieldDescriptor.basis ?? "",
        fieldDescriptor.colormap ?? "",
        fieldDescriptor.min_value,
        fieldDescriptor.max_value,
        fieldDescriptor.unit ?? "",
        fieldDescriptor.source ?? "",
        fieldDescriptor.values?.length ?? 0,
        fieldDescriptor.node_coords?.length ?? 0,
      ].join("|")
    : "";

  useEffect(() => {
    if (!hostRef.current) return;

    const host = hostRef.current;
    const getHostSize = () => ({
      width: Math.max(host.clientWidth, 1),
      height: Math.max(host.clientHeight, 1),
    });
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#08111f");
    sceneRef.current = scene;
    const highlightGroup = new THREE.Group();
    highlightGroup.name = "pointer-highlights";
    scene.add(highlightGroup);
    highlightGroupRef.current = highlightGroup;

    const initialSize = getHostSize();
    const camera = new THREE.PerspectiveCamera(45, initialSize.width / initialSize.height, 0.1, 1000);
    camera.position.set(3, 3, 5);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setSize(initialSize.width, initialSize.height, false);
    host.innerHTML = "";
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0.5, 0.5, 0.5);

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const dirLight = new THREE.DirectionalLight(0xffffff, 2);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);
    const fillLight = new THREE.DirectionalLight(0x60a5fa, 0.8);
    fillLight.position.set(-6, 4, -5);
    scene.add(fillLight);
    scene.add(new THREE.GridHelper(10, 10, 0x3b82f6, 0x334155));

    let object3d: THREE.Object3D | null = null;
    let isDisposed = false;
    const setSafeViewerState = (status: ViewerLoadState, detail: string) => {
      if (!isDisposed) {
        setViewerState({ status, detail });
      }
    };

    const resolvedFormat = resolveAssetFormat(assetUrl, assetFormat);
    const attachObject = (nextObject: THREE.Object3D) => {
      if (object3d) scene.remove(object3d);
      object3d = nextObject;
      if (fieldDescriptor?.basis === "y_normalized") {
        applyYNormalizedColors(nextObject, fieldDescriptor.colormap);
      } else if (
        fieldDescriptor?.format === "vertex_json" &&
        fieldDescriptor.values &&
        fieldDescriptor.node_coords
      ) {
        const { applied, bboxStatus, warnings } = applyFieldColors(
          nextObject,
          fieldDescriptor.values,
          fieldDescriptor.node_coords,
          fieldDescriptor.min_value,
          fieldDescriptor.max_value,
          fieldDescriptor.colormap,
        );
        if (applied && fieldDescriptor) {
          fieldDescriptor.bbox_status = bboxStatus;
          if (warnings.length && fieldDescriptor.warnings) {
            fieldDescriptor.warnings.push(...warnings);
          } else if (warnings.length) {
            fieldDescriptor.warnings = warnings;
          }
        }
      }
      scene.add(nextObject);
      if (!fitCameraToObject(camera, controls, nextObject)) {
        setSafeViewerState("error", "预览资产缺少可用的几何边界，无法定位相机");
        return;
      }
      const fieldNote = (() => {
        if (!fieldDescriptor) return "";
        const label = fieldLabel(fieldDescriptor.field_name);
        if (fieldDescriptor.source === "frd") {
          if (fieldDescriptor.bbox_status === "suspicious") {
            return ` · ${label} overlay (FRD数据存在，但几何坐标可能不一致)`;
          }
          return ` · ${label} overlay (FRD真实数据)`;
        }
        return ` · ${label} overlay (合成预览，不可用于工程判断)`;
      })();
      if (fieldDescriptor?.bbox_status === "suspicious") {
        setSafeViewerState("ready", `真实预览资产已加载${fieldNote} — 警告：FRD 坐标与几何不匹配`);
      } else {
        setSafeViewerState("ready", `真实预览资产已加载${fieldNote}`);
      }
    };

    if (assetUrl && resolvedFormat) {
      const absoluteUrl = assetUrl.startsWith("http") ? assetUrl : `${api.base}${assetUrl}`;
      setSafeViewerState("loading", `正在加载 ${resolvedFormat.toUpperCase()} 预览资产`);

      if (resolvedFormat === "glb") {
        new GLTFLoader().load(
          absoluteUrl,
          (gltf: { scene: THREE.Object3D }) => {
            attachObject(gltf.scene);
          },
          undefined,
          (error: unknown) => {
            const detail = error instanceof Error ? error.message : "GLB 预览资产加载失败";
            setSafeViewerState("error", detail);
          },
        );
      } else if (resolvedFormat === "stl") {
        new STLLoader().load(
          absoluteUrl,
          (geometry: THREE.BufferGeometry) => {
            geometry.computeVertexNormals();
            const mesh = new THREE.Mesh(
              geometry,
              new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.15, roughness: 0.6 }),
            );
            attachObject(mesh);
          },
          undefined,
          (error: unknown) => {
            const detail = error instanceof Error ? error.message : "STL 预览资产加载失败";
            setSafeViewerState("error", detail);
          },
        );
      }
    } else if (assetUrl && !resolvedFormat) {
      setSafeViewerState("error", "预览资产格式无法识别");
    } else {
      setSafeViewerState("idle", "等待生成预览资产");
    }

    const onResize = () => {
      const size = getHostSize();
      camera.aspect = size.width / size.height;
      camera.updateProjectionMatrix();
      renderer.setSize(size.width, size.height, false);
    };

    // Click-to-pointer: raycast against the loaded object and call backend
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const onClick = (event: MouseEvent) => {
      if (!host || !object3d || !projectId) return;
      const rect = host.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(object3d.children, true);
      if (intersects.length === 0) {
        setTooltipFace(null);
        return;
      }
      const hit = intersects[0];
      const pt = hit.point;
      api.pickFace(projectId, pt.x, pt.y, pt.z)
        .then((data) => {
          if (data && data.pointer) {
            const face: PickedFace = {
              pointer: data.pointer as string,
              label: (data.label as string) || (data.pointer as string),
              surface_type: (data.surface_type as string) || "unknown",
              roles: Array.isArray(data.roles) ? (data.roles as string[]) : [],
            };
            if (event.shiftKey) {
              onAddPickedFace(face);
            }
            setTooltipFace(face);
          }
        })
        .catch(() => setTooltipFace(null));
    };
    host.addEventListener("click", onClick);

    let frame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };

    const resizeObserver = new ResizeObserver(() => onResize());
    resizeObserver.observe(host);
    window.addEventListener("resize", onResize);
    animate();

    return () => {
      isDisposed = true;
      resizeObserver.disconnect();
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(frame);
      host.removeEventListener("click", onClick);
      controls.dispose();
      renderer.dispose();
      host.innerHTML = "";
      sceneRef.current = null;
      highlightGroupRef.current = null;
    };
  }, [assetFormat, assetUrl, fieldDescriptorKey]);

  // Highlight effect: paints overlay markers (wireframe bbox + center sphere)
  // for each face_id in highlightedFaceIds. The GLB pipeline exports a single
  // merged mesh ([cad_generation.py]) so true per-face material change is not
  // possible without instrumenting the export — overlays achieve the same goal
  // visually without touching the asset pipeline.
  useEffect(() => {
    const group = highlightGroupRef.current;
    if (!group) return;
    // Clear previous overlays.
    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose();
        if (Array.isArray(child.material)) {
          for (const m of child.material) m.dispose();
        } else {
          child.material.dispose();
        }
      } else if (child instanceof THREE.LineSegments || child instanceof THREE.Box3Helper) {
        (child as THREE.Object3D & { geometry?: THREE.BufferGeometry; material?: THREE.Material }).geometry?.dispose();
        (child as THREE.Object3D & { material?: THREE.Material }).material?.dispose();
      }
    }
    if (!brepSnapshot || highlightedFaceIds.size === 0) return;

    const HIGHLIGHT_COLOR = 0xfacc15; // amber/yellow
    for (const faceId of highlightedFaceIds) {
      const face = brepSnapshot.faces[faceId];
      if (!face) continue;
      const bbox = face.bounding_box;
      if (bbox && bbox.length === 6) {
        const min = new THREE.Vector3(bbox[0], bbox[1], bbox[2]);
        const max = new THREE.Vector3(bbox[3], bbox[4], bbox[5]);
        // Inflate slightly so the wireframe doesn't z-fight with the mesh.
        const size = new THREE.Vector3().subVectors(max, min);
        const diagonal = Math.max(size.length(), 1e-3);
        const inflate = diagonal * 0.02;
        min.subScalar(inflate);
        max.addScalar(inflate);
        const helper = new THREE.Box3Helper(new THREE.Box3(min, max), HIGHLIGHT_COLOR);
        // Make line material slightly thicker via depthTest=false so the box
        // is visible even when occluded behind the mesh.
        const mat = (helper as unknown as { material: THREE.LineBasicMaterial }).material;
        mat.depthTest = false;
        mat.transparent = true;
        mat.opacity = 0.95;
        helper.renderOrder = 999;
        group.add(helper);
      }
      const center = face.center;
      if (center && center.length === 3) {
        const refSize = bbox && bbox.length === 6
          ? Math.max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2])
          : 1;
        const sphereRadius = Math.max(refSize * 0.04, 0.5);
        const sphere = new THREE.Mesh(
          new THREE.SphereGeometry(sphereRadius, 16, 12),
          new THREE.MeshBasicMaterial({ color: HIGHLIGHT_COLOR, transparent: true, opacity: 0.85, depthTest: false }),
        );
        sphere.position.set(center[0], center[1], center[2]);
        sphere.renderOrder = 1000;
        group.add(sphere);
      }
    }
  }, [highlightedFaceIds, brepSnapshot]);

  return (
    <div className="viewer-canvas-shell">
      <div className="viewer-canvas" ref={hostRef} />
      {viewerState.status !== "ready" ? (
        <div className={`viewer-overlay state-${viewerState.status}`}>
          <strong>
            {viewerState.status === "error"
              ? "预览加载失败"
              : viewerState.status === "loading"
                ? "正在加载真实模型"
                : "等待预览资产"}
          </strong>
          <span>{viewerState.detail}</span>
        </div>
      ) : null}
      {tooltipFace && (
        <div className="viewer-face-tooltip">
          <div className="viewer-face-tooltip-row">
            <span className="viewer-face-tooltip-badge">{tooltipFace.surface_type}</span>
            <strong>{tooltipFace.pointer}</strong>
          </div>
          <div className="viewer-face-tooltip-label">{tooltipFace.label}</div>
          {tooltipFace.roles.length > 0 && (
            <div className="viewer-face-tooltip-roles">{tooltipFace.roles.join(", ")}</div>
          )}
          <div className="viewer-face-tooltip-actions">
            <button
              type="button"
              className="viewer-face-action-btn"
              disabled={preprocessBusy}
              onClick={() => {
                setPreprocessBusy(true);
                void onRunPreprocess(`Apply a 500 N load on ${tooltipFace.pointer}`).finally(() => setPreprocessBusy(false));
              }}
              title="AI-preprocess: 500 N load"
            >
              {preprocessBusy ? "…" : "Apply load here"}
            </button>
            <button
              type="button"
              className="viewer-face-action-btn"
              disabled={preprocessBusy}
              onClick={() => {
                setPreprocessBusy(true);
                void onRunPreprocess(`Set ${tooltipFace.pointer} as fixed support`).finally(() => setPreprocessBusy(false));
              }}
              title="AI-preprocess: fixed support"
            >
              {preprocessBusy ? "…" : "Set as support"}
            </button>
            <button
              type="button"
              className="viewer-face-action-btn secondary"
              onClick={() => onInsertToChat(tooltipFace.pointer)}
            >
              Use in chat
            </button>
          </div>
          <small>Shift+Click to multi-select</small>
        </div>
      )}
      {pickedFaces.length > 0 && (
        <div className="viewer-face-multisel">
          <div className="viewer-face-multisel-header">
            <strong>{pickedFaces.length} face{pickedFaces.length !== 1 ? "s" : ""} selected</strong>
            <button type="button" className="ghost-button compact-button" onClick={onClearPickedFaces}>
              Clear
            </button>
          </div>
          <div className="viewer-face-multisel-list">
            {pickedFaces.map((f) => (
              <div key={f.pointer} className="viewer-face-multisel-item">
                <span className="viewer-face-multisel-badge">{f.surface_type}</span>
                <code>{f.pointer}</code>
                <button
                  type="button"
                  className="viewer-face-multisel-use"
                  onClick={() => onInsertToChat(f.pointer)}
                  title="Insert into chat"
                >
                  ↵
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {highlightedFaceIds.size > 0 && (
        <div className="viewer-face-highlight-badge">
          <span>
            <strong>{highlightedFaceIds.size}</strong> face{highlightedFaceIds.size !== 1 ? "s" : ""} highlighted
          </span>
          <button type="button" className="ghost-button compact-button" onClick={onClearHighlightedFaces}>
            Clear
          </button>
        </div>
      )}
      {cadGenerationProgress && (
        <div className="viewer-cad-progress-overlay">
          <CadProgressPanel progress={cadGenerationProgress} />
        </div>
      )}
    </div>
  );
}
