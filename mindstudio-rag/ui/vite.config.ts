import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    // react-force-graph ships its own React peer; force a single copy.
    dedupe: ["react", "react-dom"],
  },
  optimizeDeps: {
    include: ["react", "react-dom", "react-dom/client"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8790",
        changeOrigin: true,
      },
    },
  },
});
