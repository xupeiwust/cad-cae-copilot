import { defineConfig } from "vite";

// The production build is served by the backend at /app/ (single UI source of
// truth for both the browser and the VS Code extension's embedded webview), so
// built asset URLs need that prefix. The dev server (npm run dev) keeps the root
// base so http://localhost:5173/ works as before.
//
// API base: the app now defaults to a same-origin (empty) API base so the
// packaged build (backend serves the SPA) works on any host port. In dev the
// SPA is served by Vite at :5173, so we proxy the backend's same-origin paths
// to 127.0.0.1:BACKEND_PORT — no VITE_API_BASE needed. Override with BACKEND_PORT.
//   /api     — REST + the SSE agent-activity stream
//   /assets  — backend StaticFiles mount for viewer assets (/assets/projects/<id>/.../model.glb).
//              The app's own bundles live under /app/assets/ (build base = /app/), and Vite
//              dev serves its modules from /src,/@vite,…, so /assets is purely backend data.
const BACKEND_PORT = process.env.BACKEND_PORT ?? "8000";
const BACKEND_TARGET = `http://127.0.0.1:${BACKEND_PORT}`;

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/app/" : "/",
  server: {
    proxy: {
      "/api": { target: BACKEND_TARGET, changeOrigin: true },
      "/assets": { target: BACKEND_TARGET, changeOrigin: true },
    },
  },
}));
