import type { LiveSyncStatus } from "../../appUtils";
import type { ChatConnection, RuntimeConfigSnapshot } from "../../types";

export type HealthTone = "ready" | "warning" | "error" | "loading" | "unknown";

export type HealthBadge = {
  id: "backend" | "events" | "agent" | "runtime";
  label: string;
  status: string;
  tone: HealthTone;
  detail: string;
};

export type ConnectionHealthArgs = {
  chatConnections: ChatConnection[];
  selectedConnectionId: string;
  selectedConnectionBlocked?: boolean;
  llmReady: boolean;
  liveSyncStatus?: LiveSyncStatus | null;
  liveSyncDetail?: string | null;
  runtime?: RuntimeConfigSnapshot | null;
  runtimeReady?: boolean | null;
  runtimeProvider?: string | null;
};

export function deriveConnectionHealth({
  chatConnections,
  selectedConnectionId,
  selectedConnectionBlocked = false,
  llmReady,
  liveSyncStatus,
  liveSyncDetail,
  runtime,
  runtimeReady,
  runtimeProvider,
}: ConnectionHealthArgs): HealthBadge[] {
  const selected = chatConnections.find((item) => item.id === selectedConnectionId) ?? chatConnections[0] ?? null;
  return [
    backendBadge(liveSyncStatus, liveSyncDetail),
    eventsBadge(liveSyncStatus, liveSyncDetail),
    agentBadge(selected, llmReady, selectedConnectionBlocked),
    runtimeBadge(runtime, runtimeReady, runtimeProvider),
  ];
}

export function ConnectionHealthBar(props: ConnectionHealthArgs) {
  const badges = deriveConnectionHealth(props);
  return (
    <div className="connection-health-bar" aria-label="Connection health">
      {badges.map((badge) => (
        <span
          key={badge.id}
          className={`connection-health-badge health-${badge.tone}`}
          title={badge.detail}
        >
          <span className="connection-health-label">{badge.label}</span>
          <span className="connection-health-status">{badge.status}</span>
        </span>
      ))}
    </div>
  );
}

function backendBadge(status?: LiveSyncStatus | null, detail?: string | null): HealthBadge {
  if (!status || status === "connecting") {
    return {
      id: "backend",
      label: "Backend",
      status: "Checking",
      tone: "loading",
      detail: detail || "Checking backend activity stream.",
    };
  }
  if (status === "live" || status === "polling") {
    return {
      id: "backend",
      label: "Backend",
      status: "Ready",
      tone: "ready",
      detail: detail || "Backend is reachable.",
    };
  }
  if (status === "reconnecting") {
    return {
      id: "backend",
      label: "Backend",
      status: "Reconnecting",
      tone: "warning",
      detail: detail || "Trying to reconnect to backend events.",
    };
  }
  return {
    id: "backend",
    label: "Backend",
    status: "Offline",
    tone: "error",
    detail: detail || "Backend activity stream is offline.",
  };
}

function eventsBadge(status?: LiveSyncStatus | null, detail?: string | null): HealthBadge {
  if (!status || status === "connecting") {
    return {
      id: "events",
      label: "Events",
      status: "Connecting",
      tone: "loading",
      detail: detail || "Connecting to the server-sent events stream.",
    };
  }
  if (status === "live") {
    return {
      id: "events",
      label: "Events",
      status: "Live",
      tone: "ready",
      detail: detail || "Live event stream is connected.",
    };
  }
  if (status === "polling") {
    return {
      id: "events",
      label: "Events",
      status: "Polling",
      tone: "warning",
      detail: detail || "SSE is unavailable; polling fallback is active.",
    };
  }
  if (status === "reconnecting") {
    return {
      id: "events",
      label: "Events",
      status: "Reconnecting",
      tone: "warning",
      detail: detail || "Event stream disconnected; browser will retry.",
    };
  }
  return {
    id: "events",
    label: "Events",
    status: "Offline",
    tone: "error",
    detail: detail || "Live event stream is offline.",
  };
}

function agentBadge(
  selected: ChatConnection | null,
  llmReady: boolean,
  selectedConnectionBlocked: boolean,
): HealthBadge {
  if (!selected) {
    return {
      id: "agent",
      label: "Agent",
      status: "Loading",
      tone: "loading",
      detail: "Loading available chat connections.",
    };
  }
  if (selectedConnectionBlocked) {
    return {
      id: "agent",
      label: "Agent",
      status: "Blocked",
      tone: "error",
      detail: selected.detail || "Selected connection is blocked for the current context.",
    };
  }
  if (selected.id === "llm-api" && !llmReady) {
    return {
      id: "agent",
      label: "Agent",
      status: "LLM needs key",
      tone: "warning",
      detail: selected.detail || "Configure a provider/model and API key or API key environment variable.",
    };
  }
  if (selected.id === "local-agent") {
    const adapters = selected.adapters ?? [];
    const available = adapters.filter((adapter) => adapter.status === "available");
    const unavailable = adapters.filter((adapter) => adapter.status !== "available");
    if (!adapters.length) {
      return {
        id: "agent",
        label: "Agent",
        status: selected.status === "ready" ? "Ready" : "Checking",
        tone: selected.status === "ready" ? "ready" : "loading",
        detail: selected.detail || "Loading local agent adapter capabilities.",
      };
    }
    if (available.length) {
      const availableNames = available.map((adapter) => adapter.label).join(", ");
      const missing = unavailable.map((adapter) => `${adapter.label}: ${adapter.diagnostic || adapter.status}`).join("; ");
      return {
        id: "agent",
        label: "Agent",
        status: `${available[0].label} ready`,
        tone: unavailable.length ? "warning" : "ready",
        detail: missing
          ? `Available: ${availableNames}. Unavailable: ${missing}.`
          : `Available local agents: ${availableNames}.`,
      };
    }
    const first = adapters[0];
    return {
      id: "agent",
      label: "Agent",
      status: "Unavailable",
      tone: "error",
      detail: first?.diagnostic || selected.detail || "No local agent adapter is available.",
    };
  }
  return {
    id: "agent",
    label: "Agent",
    status: selected.status === "ready" ? "Ready" : selected.status.replace(/_/g, " "),
    tone: connectionTone(selected.status),
    detail: selected.detail || `${selected.label} status: ${selected.status}`,
  };
}

function runtimeBadge(
  runtime?: RuntimeConfigSnapshot | null,
  runtimeReady?: boolean | null,
  runtimeProvider?: string | null,
): HealthBadge {
  if (!runtime) {
    return {
      id: "runtime",
      label: "CAD",
      status: "Checking",
      tone: "loading",
      detail: "Reading CAD runtime configuration.",
    };
  }
  const provider = runtimeProvider || runtime.config.provider || "CAD runtime";
  const issues = runtime.probe.issues?.join("; ");
  if (runtimeReady ?? runtime.probe.ready) {
    return {
      id: "runtime",
      label: "CAD",
      status: "Ready",
      tone: "ready",
      detail: `${provider} ready. Topology backend: ${runtime.probe.topology_backend_resolved}.${issues ? ` ${issues}` : ""}`,
    };
  }
  const missingCore =
    runtime.config.provider === "build123d"
      ? runtime.probe.build123d_available === false || runtime.probe.ocp_available === false
      : runtime.probe.freecad_cmd_exists === false;
  return {
    id: "runtime",
    label: "CAD",
    status: missingCore ? "Missing" : "Degraded",
    tone: missingCore ? "error" : "warning",
    detail: issues || runtime.probe.bridge_error || `${provider} is not ready.`,
  };
}

function connectionTone(status: string): HealthTone {
  if (status === "ready") return "ready";
  if (status === "blocked") return "error";
  if (status === "configurable" || status === "degraded") return "warning";
  return "unknown";
}
