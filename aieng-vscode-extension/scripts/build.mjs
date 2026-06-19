import { build, context } from "esbuild";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const watch = process.argv.includes("--watch");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

await mkdir(resolve(root, "out"), { recursive: true });
await mkdir(resolve(root, "media"), { recursive: true });

const configs = [
  {
    entryPoints: [resolve(root, "src/extension.ts")],
    outfile: resolve(root, "out/extension.js"),
    bundle: true,
    platform: "node",
    format: "cjs",
    external: ["vscode"],
    sourcemap: true,
  },
  {
    entryPoints: [resolve(root, "webview-src/main.ts")],
    outfile: resolve(root, "media/viewer.js"),
    bundle: true,
    platform: "browser",
    format: "iife",
    sourcemap: true,
  },
  {
    entryPoints: [resolve(root, "webview-src/home.ts")],
    outfile: resolve(root, "media/home.js"),
    bundle: true,
    platform: "browser",
    format: "iife",
    sourcemap: true,
  },
];

if (watch) {
  for (const config of configs) {
    const ctx = await context(config);
    await ctx.watch();
  }
  console.log("Watching extension and webview bundles...");
} else {
  await Promise.all(configs.map((config) => build(config)));
}
