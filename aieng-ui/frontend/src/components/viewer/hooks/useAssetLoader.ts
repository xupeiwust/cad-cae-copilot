import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { api } from "../../../api";
import type { ViewerLoadState } from "../../../appTypes";
import { fieldLabel, resolveAssetFormat } from "../../../appUtils";
import type { FieldOverlayConfig, SolverFieldDescriptor } from "../../../types";
import { fitCameraToObject } from "../../viewer/camera";
import { applyFieldColors, applyYNormalizedColors } from "../../viewer/fieldColors";

/**
 * Load a GLB or STL preview asset into the scene, apply optional field
 * colourmaps, fit the camera, and report load state.
 *
 * The effect re-runs whenever the asset URL, format, or field descriptor
 * changes (mirroring the original ModelViewer dependency semantics).
 */
export function useAssetLoader(
  sceneRef: React.RefObject<THREE.Scene | null>,
  cameraRef: React.RefObject<THREE.PerspectiveCamera | null>,
  controlsRef: React.RefObject<{ target: THREE.Vector3; update(): void } | null>,
  objectRef: React.MutableRefObject<THREE.Object3D | null>,
  assetUrl: string | null | undefined,
  assetFormat: string | null | undefined,
  fieldDescriptor: SolverFieldDescriptor | null | undefined,
  onObjectReady: () => void,
  setViewerState: (state: { status: ViewerLoadState; detail: string }) => void,
  fieldOverlayConfig?: FieldOverlayConfig | null,
) {
  // Stable callback refs so the effect can read the latest callbacks
  // without adding them to the dependency array.
  const onObjectReadyRef = useRef(onObjectReady);
  const setViewerStateRef = useRef(setViewerState);
  onObjectReadyRef.current = onObjectReady;
  setViewerStateRef.current = setViewerState;

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
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!scene || !camera || !controls) return;

    let object3d: THREE.Object3D | null = null;
    let isDisposed = false;

    const setSafeViewerState = (status: ViewerLoadState, detail: string) => {
      if (!isDisposed) {
        setViewerStateRef.current({ status, detail });
      }
    };

    const resolvedFormat = resolveAssetFormat(assetUrl, assetFormat);

    const attachObject = (nextObject: THREE.Object3D) => {
      if (object3d) scene.remove(object3d);
      object3d = nextObject;
      objectRef.current = nextObject;

      // Apply field colourmap if provided.
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
          fieldOverlayConfig?.colormap ?? fieldDescriptor.colormap,
          fieldOverlayConfig,
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
        setSafeViewerState(
          "ready",
          `Real preview asset loaded${fieldNote} — Warning: FRD coordinates mismatch geometry`,
        );
      } else {
        setSafeViewerState("ready", `Real preview asset loaded${fieldNote}`);
      }

      onObjectReadyRef.current();
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

    return () => {
      isDisposed = true;
      if (object3d) {
        scene.remove(object3d);
      }
      objectRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetFormat, assetUrl, fieldDescriptorKey, sceneRef, cameraRef, controlsRef, objectRef]);
}
