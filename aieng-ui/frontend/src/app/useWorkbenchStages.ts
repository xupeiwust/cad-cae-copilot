import { useCallback, useState } from "react";

import { BASE_STAGES } from "../appConstants";
import type { StageItem, StageState } from "../appTypes";

export function useWorkbenchStages() {
  const [stages, setStages] = useState<StageItem[]>(BASE_STAGES);

  const resetStages = useCallback(() => {
    setStages(BASE_STAGES.map((item) => ({ ...item, state: "idle" })));
  }, []);

  const patchStage = useCallback((key: string, state: StageState, detail?: string) => {
    setStages((current) =>
      current.map((item) =>
        item.key === key ? { ...item, state, detail: detail ?? item.detail } : item,
      ),
    );
  }, []);

  return {
    stages,
    resetStages,
    patchStage,
  };
}
