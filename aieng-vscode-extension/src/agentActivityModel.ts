type AgentActivityEvent = {
  type?: unknown;
  project_id?: unknown;
  diagnostic?: unknown;
  payload?: unknown;
};

export type ProjectActivityDiagnostic = {
  code: string;
  message: string;
  remediation?: string;
  toolName?: string;
};

export type ProjectActivityEvent = {
  type: string;
  projectId: string;
  diagnostic?: ProjectActivityDiagnostic;
};

export function projectIdFromEvent(data: unknown): string | undefined {
  return projectActivityFromEvent(data)?.projectId;
}

export function projectActivityFromEvent(data: unknown): ProjectActivityEvent | undefined {
  if (typeof data !== "string") return undefined;
  try {
    const event = JSON.parse(data) as AgentActivityEvent;
    if (typeof event.project_id !== "string" || !event.project_id.trim()) return undefined;
    const diagnostic = diagnosticFromRecord(event);
    return {
      type: typeof event.type === "string" ? event.type : "",
      projectId: event.project_id.trim(),
      ...(diagnostic ? { diagnostic } : {}),
    };
  } catch {
    return undefined;
  }
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function diagnosticFromRecord(event: AgentActivityEvent): ProjectActivityDiagnostic | undefined {
  const payload = asRecord(event.payload);
  const raw = asRecord(event.diagnostic) ?? asRecord(payload?.diagnostic);
  const code = asString(raw?.code) ?? asString(payload?.code);
  const message = asString(raw?.message) ?? asString(payload?.message) ?? asString(payload?.error);
  if (!raw || (!code && !message)) return undefined;

  const remediation = asString(raw.remediation) ?? asString(payload?.remediation);
  const toolName = asString(raw.tool_name)
    ?? asString(raw.toolName)
    ?? asString(payload?.tool_name)
    ?? asString(payload?.tool);

  return {
    code: code ?? "diagnostic",
    message: message ?? code ?? "Diagnostic",
    ...(remediation ? { remediation } : {}),
    ...(toolName ? { toolName } : {}),
  };
}

