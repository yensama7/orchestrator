import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev proxies /api to the backend so the browser talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: process.env.API_URL ?? "http://localhost:8000", changeOrigin: true },
    },
  },
});
