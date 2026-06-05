import { existsSync, readFileSync } from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";

import type { AgentMcpStatus } from "./protocol";

/**
 * Detect whether this workspace wires the `aieng-workbench` MCP server into an
 * agent, so AIENG Home can tell a first-time user whether their agent (Claude
 * Code / Codex / Copilot) can actually drive the workbench. Checks the two
 * conventional config files; detection is best-effort and never throws.
 */
export function detectAgentMcp(): AgentMcpStatus {
  const sources: string[] = [];
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const root = folder.uri.fsPath;
    if (hasAiengServer(path.join(root, ".mcp.json"), "mcpServers")) sources.push(".mcp.json (Claude Code)");
    if (hasAiengServer(path.join(root, ".vscode", "mcp.json"), "servers")) sources.push(".vscode/mcp.json (Copilot / VS Code)");
  }
  const configured = sources.length > 0;
  return {
    configured,
    sources,
    detail: configured
      ? `AIENG tools available to your agent via ${sources.join(", ")}`
      : "No aieng-workbench MCP server found in this workspace",
  };
}

function hasAiengServer(file: string, key: "mcpServers" | "servers"): boolean {
  try {
    if (!existsSync(file)) return false;
    const parsed = JSON.parse(readFileSync(file, "utf8")) as Record<string, unknown>;
    const servers = parsed?.[key];
    if (!servers || typeof servers !== "object") return false;
    return Object.entries(servers as Record<string, unknown>).some(([name, config]) => {
      if (name.toLowerCase().includes("aieng")) return true;
      const cfg = (config ?? {}) as { args?: unknown; cwd?: unknown };
      const args = Array.isArray(cfg.args) ? cfg.args.join(" ") : "";
      const cwd = typeof cfg.cwd === "string" ? cfg.cwd : "";
      return /mcp_server|aieng/i.test(args) || /aieng/i.test(cwd);
    });
  } catch {
    return false;
  }
}
