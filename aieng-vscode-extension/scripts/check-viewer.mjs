import { readFile } from "node:fs/promises";

const source = await readFile("webview-src/main.ts", "utf8");

if (!source.includes("[hidden] { display:none !important; }")) {
  throw new Error("Viewer CSS must explicitly hide elements carrying the hidden attribute.");
}

if (!source.includes("empty.hidden = true;")) {
  throw new Error("Viewer must hide the empty state before loading a preview asset.");
}
