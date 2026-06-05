import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { api } from "../api";
import type { BrepGraphSnapshot, CadGenerationProgress, PickedFace, ViewerLoadState } from "../appTypes";
import { fieldLabel, resolveAssetFormat } from "../appUtils";
import type { SolverFieldDescriptor } from "../types";
import { fitCameraToObject } from "./viewer/camera";
import {
  IDENTITY_TRANSFORM,
  deriveGlbScale,
  displayToModelPoint,
  type DisplayTransform,
} from "./viewer/coordinateFrames";
import { buildFaceIdentityMaps } from "./viewer/faceIdentity";
import { applyFieldColors, applyYNormalizedColors } from "./viewer/fieldColors";
import { createFaceHighlightMesh, createPrimitiveOverlay, disposeHighlightObject } from "./viewer/highlights";
import { ViewerOverlays } from "./viewer/ViewerOverlays";

export function ModelViewer({
  assetUrl,
  assetFormat,
  fieldDescriptor,
  projectId,
  pickedFaces,
  onAddPickedFace,
  onClearPickedFaces,
  onCopyPointer,
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
  onCopyPointer(text: string): void;
  cadGenerationProgress: CadGenerationProgress | null;
  highlightedFaceIds: Set<string>;
  brepSnapshot: BrepGraphSnapshot | null;
  onClearHighlightedFaces(): void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  // Scene refs shared between the asset-loading effect and the highlight effect.
  const sceneRef = useRef<THREE.Scene | null>(null);
  const highlightGroupRef = useRef<THREE.Group | null>(null);
  const objectRef = useRef<THREE.Object3D | null>(null);
  const [objectReadyKey, setObjectReadyKey] = useState(0);
  const [viewerState, setViewerState] = useState<{ status: ViewerLoadState; detail: string }>({
    status: "idle",
    detail: "Waiting for preview asset",
  });
  const [tooltipFace, setTooltipFace] = useState<PickedFace | null>(null);
  // Viewer↔model coordinate transform (see DisplayTransform). Held in a ref so
  // the click handler always reads the current value without re-binding.
  const displayTransformRef = useRef<DisplayTransform>(IDENTITY_TRANSFORM);
  // Identity maps from displayed primitive ↔ B-Rep face (built once per load),
  // so pick + highlight resolve exact faces instead of geometry-guessing.
  const primitiveFaceRef = useRef<Map<THREE.Object3D, PickedFace>>(new Map());
  const faceMeshesRef = useRef<Map<string, THREE.Mesh[]>>(new Map());
  const resolvedAssetFormat = resolveAssetFormat(assetUrl, assetFormat);
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
    scene.background = new THREE.Color("#111111");
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

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
    fillLight.position.set(-6, 4, -5);
    scene.add(fillLight);
    scene.add(new THREE.GridHelper(10, 10, 0x333333, 0x222222));

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
      objectRef.current = nextObject;
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
        setSafeViewerState("error", "Preview asset missing valid geometry bounds, cannot position camera");
        return;
      }
      const fieldNote = (() => {
        if (!fieldDescriptor) return "";
        const label = fieldLabel(fieldDescriptor.field_name);
        if (fieldDescriptor.source === "frd") {
          if (fieldDescriptor.bbox_status === "suspicious") {
            return ` · ${label} overlay (FRD data present, but geometry coordinates may mismatch)`;
          }
          return ` · ${label} overlay (FRD real data)`;
        }
        return ` · ${label} overlay (synthetic preview, not for engineering decisions)`;
      })();
      if (fieldDescriptor?.bbox_status === "suspicious") {
        setSafeViewerState("ready", `Real preview asset loaded${fieldNote} — Warning: FRD coordinates mismatch geometry`);
      } else {
        setSafeViewerState("ready", `Real preview asset loaded${fieldNote}`);
      }
      setObjectReadyKey((current) => current + 1);
    };

    if (assetUrl && resolvedFormat) {
      const absoluteUrl = assetUrl.startsWith("http") ? assetUrl : `${api.base}${assetUrl}`;
      setSafeViewerState("loading", `Loading ${resolvedFormat.toUpperCase()} preview asset`);

      if (resolvedFormat === "glb") {
        new GLTFLoader().load(
          absoluteUrl,
          (gltf: { scene: THREE.Object3D }) => {
            attachObject(gltf.scene);
          },
          undefined,
          (error: unknown) => {
            const detail = error instanceof Error ? error.message : "GLB preview asset failed to load";
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
              new THREE.MeshStandardMaterial({ color: 0xaaaaaa, metalness: 0.15, roughness: 0.6 }),
            );
            attachObject(mesh);
          },
          undefined,
          (error: unknown) => {
            const detail = error instanceof Error ? error.message : "STL preview asset failed to load";
            setSafeViewerState("error", detail);
          },
        );
      }
    } else if (assetUrl && !resolvedFormat) {
      setSafeViewerState("error", "Preview asset format not recognized");
    } else {
      setSafeViewerState("idle", "Waiting for preview asset");
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
      const pickTargets = object3d instanceof THREE.Mesh ? [object3d] : object3d.children;
      const intersects = raycaster.intersectObjects(pickTargets, true);
      if (intersects.length === 0) {
        setTooltipFace(null);
        return;
      }
      const hit = intersects[0];
      // Fast path: the hit primitive is already mapped to its B-Rep face, so
      // resolve the selection locally — exact face, no backend round-trip.
      const mappedFace = primitiveFaceRef.current.get(hit.object);
      if (mappedFace) {
        onAddPickedFace(mappedFace);
        setTooltipFace(mappedFace);
        return;
      }
      // Fallback (older packages, or B-Rep snapshot not loaded yet): convert
      // the hit point to the model frame and let the backend resolve the face.
      const pt = displayToModelPoint(hit.point, displayTransformRef.current);
      api.pickFace(projectId, pt.x, pt.y, pt.z)
        .then((data) => {
          if (data && data.pointer) {
            const face: PickedFace = {
              pointer: data.pointer as string,
              label: (data.label as string) || (data.pointer as string),
              surface_type: (data.surface_type as string) || "unknown",
              roles: Array.isArray(data.roles) ? (data.roles as string[]) : [],
            };
            onAddPickedFace(face);
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
      objectRef.current = null;
    };
  }, [assetFormat, assetUrl, fieldDescriptorKey]);

  // Keep the viewer↔model transform current whenever the object or B-Rep
  // snapshot changes. Declared before the highlight effect so the ref is set
  // before highlights (and any click) are processed.
  useEffect(() => {
    const object = objectRef.current;
    const isGlb = (resolvedAssetFormat ?? "").toLowerCase() === "glb";
    if (!object || !isGlb) {
      displayTransformRef.current = IDENTITY_TRANSFORM;
      primitiveFaceRef.current = new Map();
      faceMeshesRef.current = new Map();
      return;
    }
    const transform: DisplayTransform = { scale: deriveGlbScale(object, brepSnapshot), isGlb: true };
    displayTransformRef.current = transform;
    const maps = brepSnapshot ? buildFaceIdentityMaps(object, brepSnapshot, transform) : null;
    primitiveFaceRef.current = maps?.primitiveToFace ?? new Map();
    faceMeshesRef.current = maps?.faceToPrimitives ?? new Map();
  }, [objectReadyKey, brepSnapshot, resolvedAssetFormat]);

  // Highlight effect: extracts displayed mesh triangles whose centroids match
  // the selected B-Rep face metadata, then paints a translucent face overlay.
  useEffect(() => {
    const group = highlightGroupRef.current;
    if (!group) return;
    // Clear previous overlays.
    while (group.children.length > 0) {
      const child = group.children.pop()!;
      group.remove(child);
      disposeHighlightObject(child);
    }
    if (highlightedFaceIds.size === 0) return;

    // Preferred: overlay the exact tessellated primitive for each selected face
    // (works for planar and curved faces alike).
    const faceMeshes = faceMeshesRef.current;
    if (faceMeshes.size > 0) {
      for (const faceId of highlightedFaceIds) {
        for (const prim of faceMeshes.get(faceId) ?? []) {
          group.add(createPrimitiveOverlay(prim));
        }
      }
      return;
    }

    // Fallback: reconstruct the overlay by matching mesh triangles to the
    // face bbox/normal (older packages without an identity map).
    if (!brepSnapshot) return;
    const object = objectRef.current;
    if (!object) return;
    const transform = displayTransformRef.current;
    for (const faceId of highlightedFaceIds) {
      const face = brepSnapshot.faces[faceId];
      if (!face) continue;
      const highlightMesh = createFaceHighlightMesh(object, face, transform);
      if (highlightMesh) group.add(highlightMesh);
    }
  }, [highlightedFaceIds, brepSnapshot, objectReadyKey]);

  return (
    <div className="viewer-canvas-shell">
      <div className="viewer-canvas" ref={hostRef} />
      <ViewerOverlays
        viewerState={viewerState}
        tooltipFace={tooltipFace}
        pickedFaces={pickedFaces}
        highlightedFaceIds={highlightedFaceIds}
        cadGenerationProgress={cadGenerationProgress}
        onCopyPointer={onCopyPointer}
        onClearPickedFaces={onClearPickedFaces}
        onClearHighlightedFaces={onClearHighlightedFaces}
      />
    </div>
  );
}
