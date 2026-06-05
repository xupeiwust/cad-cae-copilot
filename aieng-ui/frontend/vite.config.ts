import { defineConfig } from "vite";

// The production build is served by the backend at /app/ (single UI source of
// truth for both the browser and the VS Code extension's embedded webview), so
// built asset URLs need that prefix. The dev server (npm run dev) keeps the root
// base so http://localhost:5173/ works as before.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/app/" : "/",
}));
