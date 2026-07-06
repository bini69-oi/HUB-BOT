import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// SPA is served under /admin/ by the backend (FastAPI static mount / nginx).
export default defineConfig({
  plugins: [react()],
  base: "/admin/",
  server: {
    port: 5199,
    proxy: {
      // Vite dev proxies API calls to the local FastAPI instance.
      "/api": { target: "http://127.0.0.1:8811", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
