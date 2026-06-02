import { DEFAULT_CHAT_CONNECTIONS } from "../appConstants";
import { test } from "vitest";

test("default chat connections", () => {

function expect(condition: unknown, message: string) {
  if (!condition) throw new Error(message);
}

const ids = DEFAULT_CHAT_CONNECTIONS.map((connection) => connection.id);
const labels = DEFAULT_CHAT_CONNECTIONS.map((connection) => connection.label);

expect(ids.includes("llm-api"), "LLM API connection should remain available");
expect(ids.includes("local-agent"), "Local Agent connection should remain available");
expect(!ids.includes("external-cad-adapter"), "External CAD adapter should not be shown in Web Chat");
expect(!labels.some((label) => /external cad adapter/i.test(label)), "External CAD adapter label should not be shown");
});
