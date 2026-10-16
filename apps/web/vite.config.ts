import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const target = process.env.GSM_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { strictPort: true, proxy: { "/api": { target }, "/health": { target } } },
  preview: { strictPort: true, proxy: { "/api": { target }, "/health": { target } } },
});
