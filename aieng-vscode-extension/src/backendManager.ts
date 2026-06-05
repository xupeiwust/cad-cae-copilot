import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";

export type BackendManagerState = {
  mode: "external" | "managed" | "stopped";
  running: boolean;
  commandLine: string;
  cwd?: string;
  lastMessage?: string;
};

export class BackendManager implements vscode.Disposable {
  private process: ChildProcessWithoutNullStreams | undefined;
  private lastMessage: string | undefined;

  state(): BackendManagerState {
    const commandLine = `${this.command()} ${this.args().join(" ")}`;
    return {
      mode: this.process ? "managed" : "stopped",
      running: Boolean(this.process),
      commandLine,
      cwd: this.cwd(),
      lastMessage: this.lastMessage,
    };
  }

  async start(): Promise<BackendManagerState> {
    if (this.process) return this.state();
    const cwd = this.cwd();
    if (!cwd) {
      throw new Error("Could not find aieng-ui/backend in the current VS Code workspace.");
    }
    const command = this.command();
    const args = this.args();
    this.lastMessage = `Starting ${command} ${args.join(" ")}`;
    this.process = spawn(command, args, {
      cwd,
      shell: process.platform === "win32",
      windowsHide: true,
    });
    this.process.stdout.on("data", (chunk: Buffer) => {
      this.lastMessage = chunk.toString("utf8").trim().slice(-500);
    });
    this.process.stderr.on("data", (chunk: Buffer) => {
      this.lastMessage = chunk.toString("utf8").trim().slice(-500);
    });
    this.process.on("exit", (code) => {
      this.lastMessage = code === null ? "Managed backend stopped." : `Managed backend exited with code ${code}.`;
      this.process = undefined;
    });
    this.process.on("error", (error) => {
      this.lastMessage = error.message;
      this.process = undefined;
    });
    return this.state();
  }

  stop(): void {
    const child = this.process;
    if (!child) return;
    this.process = undefined;
    this.lastMessage = "Stopping managed backend.";
    if (process.platform === "win32" && child.pid) {
      spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true });
      return;
    }
    child.kill();
  }

  dispose(): void {
    this.stop();
  }

  private command(): string {
    return vscode.workspace.getConfiguration("aieng").get<string>("backendStartCommand", "conda");
  }

  private args(): string[] {
    return vscode.workspace.getConfiguration("aieng").get<string[]>("backendStartArgs", [
      "run",
      "-n",
      "aieng311",
      "--no-capture-output",
      "python",
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
    ]);
  }

  private cwd(): string | undefined {
    const configured = vscode.workspace.getConfiguration("aieng").get<string>("backendCwd", "").trim();
    if (configured) return configured;
    for (const folder of vscode.workspace.workspaceFolders ?? []) {
      const candidate = path.join(folder.uri.fsPath, "aieng-ui", "backend");
      if (existsSync(path.join(candidate, "app", "main.py"))) return candidate;
    }
    return undefined;
  }
}
