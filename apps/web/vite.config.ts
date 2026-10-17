import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // Server configuration only. No GSM_* values are defined in the browser bundle.
  const env = loadEnv(mode, fileURLToPath(new URL("../..", import.meta.url)), "GSM_");
  const target =
    process.env.GSM_API_PROXY_TARGET || env.GSM_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const realtime =
    process.env.GSM_REALTIME_PROXY_TARGET ||
    env.GSM_REALTIME_PROXY_TARGET ||
    "http://127.0.0.1:3001";
  const proxy = {
    "/api": { target },
    "/health": { target },
    "/trpc": { target: realtime, ws: true },
  };
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: { strictPort: true, proxy },
    preview: { strictPort: true, proxy },
  };
});
