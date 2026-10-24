import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API lives on :3000. Proxying from Vite keeps requests same-origin, so no CORS changes.
const api = "http://localhost:3000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/health": api,
      "/chat": api,
      "/sessions": api,
    },
  },
});
