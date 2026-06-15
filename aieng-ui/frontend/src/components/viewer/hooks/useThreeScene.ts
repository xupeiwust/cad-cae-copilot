import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

// OrbitControls is imported as a value (constructor).  We alias the instance
// type so we can store it in a ref without tripping over the namespace/type
// duality that some @types/three versions emit.
type OrbitControlsInstance = InstanceType<typeof OrbitControls>;

/**
 * Initialise and manage the Three.js scene lifecycle:
 * - Scene, camera, renderer, orbit controls
 * - Lighting, grid helper
 * - Resize handling (ResizeObserver + window resize)
 * - Animation loop (requestAnimationFrame)
 *
 * Returns refs for all created objects so sibling hooks can read them
 * without causing re-renders.
 */
export function useThreeScene(hostRef: React.RefObject<HTMLDivElement | null>) {
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControlsInstance | null>(null);
  const highlightGroupRef = useRef<THREE.Group | null>(null);
  const assemblyGroupRef = useRef<THREE.Group | null>(null);
  const markerGroupRef = useRef<THREE.Group | null>(null);
  const fieldRegionGroupRef = useRef<THREE.Group | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    const host = hostRef.current;

    const getHostSize = () => ({
      width: Math.max(host.clientWidth, 1),
      height: Math.max(host.clientHeight, 1),
    });

    // ── Scene ──
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#111111");
    sceneRef.current = scene;

    // ── Overlay groups ──
    const highlightGroup = new THREE.Group();
    highlightGroup.name = "pointer-highlights";
    scene.add(highlightGroup);
    highlightGroupRef.current = highlightGroup;

    const assemblyGroup = new THREE.Group();
    assemblyGroup.name = "assembly-check-group";
    scene.add(assemblyGroup);
    assemblyGroupRef.current = assemblyGroup;

    const markerGroup = new THREE.Group();
    markerGroup.name = "field-marker-group";
    scene.add(markerGroup);
    markerGroupRef.current = markerGroup;

    const fieldRegionGroup = new THREE.Group();
    fieldRegionGroup.name = "field-region-group";
    scene.add(fieldRegionGroup);
    fieldRegionGroupRef.current = fieldRegionGroup;

    // ── Camera ──
    const initialSize = getHostSize();
    const camera = new THREE.PerspectiveCamera(45, initialSize.width / initialSize.height, 0.1, 1000);
    camera.position.set(3, 3, 5);
    cameraRef.current = camera;

    // ── Renderer ──
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setSize(initialSize.width, initialSize.height, false);
    host.innerHTML = "";
    host.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // ── Controls ──
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0.5, 0.5, 0.5);
    controlsRef.current = controls;

    // ── Lights ──
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.4);
    fillLight.position.set(-6, 4, -5);
    scene.add(fillLight);
    scene.add(new THREE.GridHelper(10, 10, 0x333333, 0x222222));

    // ── Resize ──
    const onResize = () => {
      const size = getHostSize();
      camera.aspect = size.width / size.height;
      camera.updateProjectionMatrix();
      renderer.setSize(size.width, size.height, false);
    };
    const resizeObserver = new ResizeObserver(() => onResize());
    resizeObserver.observe(host);
    window.addEventListener("resize", onResize);

    // ── Animation loop ──
    let frame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();

    // ── Cleanup ──
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(frame);
      controls.dispose();
      renderer.dispose();
      host.innerHTML = "";
      sceneRef.current = null;
      highlightGroupRef.current = null;
      assemblyGroupRef.current = null;
      markerGroupRef.current = null;
      fieldRegionGroupRef.current = null;
      cameraRef.current = null;
      rendererRef.current = null;
      controlsRef.current = null;
    };
  }, [hostRef]);

  return {
    sceneRef,
    cameraRef,
    rendererRef,
    controlsRef,
    highlightGroupRef,
    assemblyGroupRef,
    markerGroupRef,
    fieldRegionGroupRef,
  };
}
