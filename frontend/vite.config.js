import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development the Vite server proxies /api to Flask, so the browser
// talks to one origin. Change the target if the backend runs elsewhere.
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: true } },
  },
});
