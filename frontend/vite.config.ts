import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In dev, proxy API calls to the FastAPI backend. In production the `web`
// nginx container proxies `/api` to the `api` service instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
