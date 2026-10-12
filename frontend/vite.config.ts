import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// Dev proxies /api (REST + SSE stream) to the FastAPI backend so the frontend is
// same-origin, exactly as the nginx build will be in compose (Phase 6).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src/renderer", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true, // SSE/websocket passthrough for /api/runs/:id/stream
      },
    },
  },
});
