import { defineConfig } from "vite";

// The production build is served by the backend at /app/ (single UI source of
// truth for both the browser and the VS Code extension's embedded webview), so
// built asset URLs need that prefix. The dev server (npm run dev) keeps the root
// base so http://localhost:5173/ works as before.
//
// API base: the app now defaults to a same-origin (empty) API base so the
// packaged build (backend serves the SPA) works on any host port. In dev the
// SPA is served by Vite at :5173, so we proxy /api (incl. the SSE activity
// stream) to the backend at 127.0.0.1:BACKEND_PORT — same-origin from the
// browser's view, no VITE_API_BASE needed. Override the target with BACKEND_PORT.
const BACKEND_PORT = process.env.BACKEND_PORT ?? "8000";
const BACKEND_TARGET = `http://127.0.0.1:${BACKEND_PORT}`;

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/app/" : "/",
  server: {
    proxy: {
      "/api": {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
    },
  },
}));
