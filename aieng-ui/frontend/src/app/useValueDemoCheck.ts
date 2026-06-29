import { useEffect, useState } from "react";

import { api } from "../api";
import type { ValueDemoCheckResponse } from "../types";

type UseValueDemoCheckArgs = {
  selectedId: string | null;
  geometryVersion?: string | null;
};

export function useValueDemoCheck({ selectedId, geometryVersion = null }: UseValueDemoCheckArgs) {
  const [valueDemoCheck, setValueDemoCheck] = useState<ValueDemoCheckResponse | null>(null);

  useEffect(() => {
    setValueDemoCheck(null);
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) return;
    void (async () => {
      try {
        const data = await api.getValueDemoCheck(selectedId, controller.signal);
        if (!controller.signal.aborted) setValueDemoCheck(data ?? null);
      } catch {
        if (!controller.signal.aborted) setValueDemoCheck(null);
      }
    })();
    return () => controller.abort();
  }, [selectedId, geometryVersion]);

  return { valueDemoCheck };
}
