export type PreviewFormat = "glb" | "stl";

export type FaceEntity = {
  id: string;
  pointer: string;
  label: string;
  surfaceType: string;
  roles: string[];
  bodyId?: string;
  center?: [number, number, number];
  boundingBox?: [number, number, number, number, number, number];
};

export type PreviewPayload = {
  kind: "preview";
  title: string;
  source: "package" | "live";
  format?: PreviewFormat;
  assetBase64?: string;
  faces: Record<string, FaceEntity>;
  facePicking: "reliable" | "unavailable";
  detail: string;
  projectId?: string;
  projectName?: string;
  backendUrl?: string;
  emptyReason?: "no_preview";
  updatedAt?: string;
};

export type HostToWebviewMessage = PreviewPayload | {
  kind: "status";
  tone: "info" | "error";
  detail: string;
};

export type WebviewToHostMessage =
  | { kind: "ready" }
  | { kind: "copy"; text: string }
  | { kind: "copyStarterPrompt" }
  | { kind: "copyModifyPrompt"; pointers?: string[] }
  | { kind: "copyProjectContext" }
  | { kind: "openHome" }
  | { kind: "refresh" };

export type HomeProject = {
  id: string;
  name: string;
  status?: string;
  updatedAt?: string;
  namedParts: string[];
};

export type AgentMcpStatus = {
  configured: boolean;
  sources: string[];
  detail: string;
};

export type HomeStateMessage = {
  kind: "homeState";
  backendUrl: string;
  status: "connected" | "unreachable";
  backendMode: "external" | "managed" | "stopped";
  projects: HomeProject[];
  detail: string;
  startCommand?: string;
  agentMcp: AgentMcpStatus;
};

export type HomeToWebviewMessage = HomeStateMessage | {
  kind: "homeBusy";
  busy: boolean;
  detail?: string;
} | {
  kind: "homeToast";
  tone: "info" | "error";
  detail: string;
};

export type HomeWebviewMessage =
  | { kind: "ready" }
  | { kind: "retry" }
  | { kind: "startBackend" }
  | { kind: "stopBackend" }
  | { kind: "createProject" }
  | { kind: "openLiveProject"; projectId?: string }
  | { kind: "openPackage" }
  | { kind: "copyStarterPrompt"; projectId: string; projectName?: string }
  | { kind: "copyModifyPrompt"; projectId: string; projectName?: string }
  | { kind: "copyProjectContext"; projectId: string; projectName?: string };
