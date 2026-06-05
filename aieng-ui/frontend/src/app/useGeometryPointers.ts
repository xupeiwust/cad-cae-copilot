import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";

import { api } from "../api";
import type { BrepGraphSnapshot, Notice, PickedFace, SelectedGeometryContext } from "../appTypes";
import { parseBrepGraphSnapshot } from "../appUtils";
import type { PointerToken } from "../components/PointerText";

type UseGeometryPointersArgs = {
  selectedId: string | null;
  // Changes when the selected project's geometry is rebuilt; triggers a
  // B-Rep snapshot re-fetch (without clearing the current selection).
  geometryVersion?: string | null;
  setMessage: Dispatch<SetStateAction<string>>;
  setNotice: Dispatch<SetStateAction<Notice | null>>;
  executePreprocessFromPrompt(prompt: string): Promise<void>;
};

export function useGeometryPointers({
  selectedId,
  geometryVersion = null,
  setMessage,
  setNotice,
  executePreprocessFromPrompt,
}: UseGeometryPointersArgs) {
  const [pickedFaces, setPickedFaces] = useState<PickedFace[]>([]);
  const [highlightedFaceIds, setHighlightedFaceIds] = useState<Set<string>>(() => new Set());
  const [brepSnapshot, setBrepSnapshot] = useState<BrepGraphSnapshot | null>(null);

  useEffect(() => {
    setHighlightedFaceIds(new Set());
    setBrepSnapshot(null);
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) return;
    void (async () => {
      try {
        let raw: Record<string, unknown>;
        try {
          raw = await api.getBrepGraph(selectedId);
        } catch {
          raw = await api.buildBrepGraph(selectedId);
        }
        if (cancelled) return;
        setBrepSnapshot(parseBrepGraphSnapshot(raw));
      } catch {
        if (!cancelled) setBrepSnapshot(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // geometryVersion re-fetches the graph after an in-place geometry rebuild
    // (e.g. agent cad.execute_build123d) so highlight + pick track new faces.
  }, [selectedId, geometryVersion]);

  function selectedGeometryContext(): SelectedGeometryContext | null {
    if (!pickedFaces.length) return null;
    return {
      pointers: pickedFaces.map((face) => face.pointer),
      faces: pickedFaces,
      highlightedFaceIds: Array.from(highlightedFaceIds),
    };
  }

  function withSelectedGeometryPrompt(prompt: string) {
    if (prompt.includes("\n\nSelected geometry:\n")) return prompt;
    const context = selectedGeometryContext();
    if (!context) return prompt;
    const faceLines = context.faces.map((face) => {
      const roles = face.roles.length ? face.roles.join(", ") : "unknown";
      return `- ${face.pointer} ${face.surface_type || "unknown"} roles: ${roles} label: ${face.label}`;
    });
    return `User request:\n${prompt}\n\nSelected geometry:\n${faceLines.join("\n")}`;
  }

  function agentPayloadGeometry() {
    return selectedGeometryContext() ?? undefined;
  }

  function addPickedFace(face: PickedFace) {
    setPickedFaces((prev) => {
      const filtered = prev.filter((item) => item.pointer !== face.pointer);
      return [face, ...filtered].slice(0, 10);
    });
    const faceId = face.pointer.startsWith("@face:") ? face.pointer.slice("@face:".length) : null;
    if (faceId) {
      setHighlightedFaceIds((prev) => {
        const next = new Set(prev);
        next.add(faceId);
        return next;
      });
    }
  }

  function clearPickedFaces() {
    setPickedFaces([]);
  }

  function insertToChat(text: string) {
    setMessage((prev) => (prev ? prev + " " + text : text));
  }

  async function runPreprocessFromPointer(prompt: string) {
    await executePreprocessFromPrompt(prompt);
  }

  const toggleHighlightedFace = useCallback((faceId: string) => {
    setHighlightedFaceIds((prev) => {
      const next = new Set(prev);
      if (next.has(faceId)) next.delete(faceId);
      else next.add(faceId);
      return next;
    });
  }, []);

  const addHighlightedFaces = useCallback((faceIds: string[]) => {
    if (!faceIds.length) return;
    setHighlightedFaceIds((prev) => {
      const next = new Set(prev);
      faceIds.forEach((faceId) => next.add(faceId));
      return next;
    });
  }, []);

  function clearHighlightedFaces() {
    setHighlightedFaceIds(new Set());
  }

  // Replace the highlight set with exactly these faces (used by node selection:
  // clicking a Shape IR node highlights precisely its viewer_selectable_ids).
  function setHighlightedFacesExact(faceIds: string[]) {
    setHighlightedFaceIds(new Set(faceIds));
  }

  const handlePointerClick = useCallback((token: PointerToken) => {
    if (token.kind === "face") {
      toggleHighlightedFace(token.id);
      return;
    }
    if (token.kind === "feature") {
      const faces = brepSnapshot?.featureFaces[token.id]
        ?? brepSnapshot?.groups[token.id]?.members
        ?? [];
      if (faces.length > 0) {
        addHighlightedFaces(faces);
      } else {
        setNotice({ tone: "info", title: "Feature not in B-Rep graph", detail: `No face mapping for @feature:${token.id}. Build the B-Rep graph first.` });
      }
      return;
    }
    if (token.kind === "group") {
      const faces = brepSnapshot?.groups[token.id]?.members ?? [];
      if (faces.length > 0) {
        addHighlightedFaces(faces);
      } else {
        setNotice({ tone: "info", title: "Group has no members", detail: `@group:${token.id}` });
      }
      return;
    }
    if (token.kind === "artifact") {
      try {
        void navigator.clipboard?.writeText(token.id);
        setNotice({ tone: "info", title: "Artifact path copied", detail: token.id });
      } catch {
        setNotice({ tone: "info", title: "Artifact", detail: token.id });
      }
      return;
    }
    setNotice({ tone: "info", title: `@${token.kind}:${token.id}`, detail: "No viewer action wired for this pointer kind yet." });
  }, [brepSnapshot, setNotice, toggleHighlightedFace, addHighlightedFaces]);

  const pointerContextValue = useMemo(
    () => ({ highlightedFaceIds, onClickPointer: handlePointerClick }),
    [highlightedFaceIds, handlePointerClick],
  );

  return {
    pickedFaces,
    highlightedFaceIds,
    brepSnapshot,
    addPickedFace,
    clearPickedFaces,
    insertToChat,
    runPreprocessFromPointer,
    clearHighlightedFaces,
    setHighlightedFacesExact,
    selectedGeometryContext,
    withSelectedGeometryPrompt,
    agentPayloadGeometry,
    pointerContextValue,
  };
}
