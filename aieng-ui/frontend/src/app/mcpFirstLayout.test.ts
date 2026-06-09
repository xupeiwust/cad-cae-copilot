import { test } from "vitest";
import appChrome from "./AppChrome.tsx?raw";
import workbenchApp from "./useWorkbenchApp.ts?raw";
import sessionsSidebar from "../components/SessionsSidebar.tsx?raw";

function expect(condition: unknown, message: string) {
  if (!condition) throw new Error(message);
}

test("active workbench shell is MCP-first and does not render embedded chat", () => {
  expect(!appChrome.includes("ChatPanel"), "AppChrome must not import/render ChatPanel");
  expect(!appChrome.includes("chat-pane"), "AppChrome must not render the old chat-pane rail");
  expect(!workbenchApp.includes("useAgentRuns"), "useWorkbenchApp must not wire embedded agent runs");
  expect(!workbenchApp.includes("DEFAULT_CHAT_CONNECTIONS"), "useWorkbenchApp must not wire default chat connections");
  expect(!sessionsSidebar.includes("chatSessions"), "SessionsSidebar must not render chat session history");
});

test("embedded VS Code workbench omits the project sidebar", () => {
  expect(appChrome.includes("{!embed && (\n            <SessionsSidebar"), "embed mode must give the full width to the viewer");
  expect(appChrome.includes('"app-main embed-main"'), "embed mode must use the single-column app-main layout");
});
