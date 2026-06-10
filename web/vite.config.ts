import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev proxy: the API runs on :8000, the Vite dev server on :5173.
// In production FastAPI serves the built assets from the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/health": "http://localhost:8000",
      "/sensors": "http://localhost:8000",
      "/actuators": "http://localhost:8000",
      "/twin": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
