import { build, context } from "esbuild";
import { mkdir } from "node:fs/promises";

const watch = process.argv.includes("--watch");
await mkdir("out", { recursive: true });
await mkdir("media", { recursive: true });

const configs = [
  {
    entryPoints: ["src/extension.ts"],
    outfile: "out/extension.js",
    bundle: true,
    platform: "node",
    format: "cjs",
    external: ["vscode"],
    sourcemap: true,
  },
  {
    entryPoints: ["webview-src/main.ts"],
    outfile: "media/viewer.js",
    bundle: true,
    platform: "browser",
    format: "iife",
    sourcemap: true,
  },
  {
    entryPoints: ["webview-src/home.ts"],
    outfile: "media/home.js",
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
