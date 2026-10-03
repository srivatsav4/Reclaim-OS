/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 700, rollupOptions: { output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom"] } } } },
  server: { port: 5173, proxy: { "/api": process.env.VITE_API_TARGET || "http://127.0.0.1:8000" } },
  test: { environment: "node" },
});
