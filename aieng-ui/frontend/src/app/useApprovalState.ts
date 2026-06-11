import { useCallback, useState } from "react";

import { api } from "../api";
import type { Notice } from "../appTypes";
import type { PendingApproval } from "./pendingApprovals";
import type { AgentTranscriptEvent } from "./chatTranscript";
import { applyApprovalEvent } from "./pendingApprovals";

type SetNotice = (notice: Notice | null) => void;

export function useApprovalState({ setNotice }: { setNotice: SetNotice }) {
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);

  const handleAgentEvent = useCallback((event: AgentTranscriptEvent) => {
    setPendingApprovals((current) => applyApprovalEvent(current, event));
  }, []);

  const resolveApproval = useCallback(async (permissionId: string, approved: boolean) => {
    setPendingApprovals((current) => current.filter((item) => item.permissionId !== permissionId));
    try {
      await api.resolveAgenticPermission(permissionId, approved);
    } catch (error) {
      setNotice({
        tone: "error",
        title: "Approval action failed",
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }, [setNotice]);

  return {
    pendingApprovals,
    handleAgentEvent,
    resolveApproval,
  };
}
