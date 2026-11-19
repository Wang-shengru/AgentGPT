import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api and /ws to the backend API_PORT (default 8001) from the root .env
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const api = `http://127.0.0.1:${env.API_PORT || "8001"}`;
  return {
    plugins: [react()],
    css: { postcss: { plugins: [] } }, // isolate from any parent-folder PostCSS config
    server: {
      port: 5173,
      proxy: {
        "/api": api,
        "/ws": { target: api.replace("http", "ws"), ws: true },
      },
    },
  };
});
