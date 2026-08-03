import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [
    react({
      jsxRuntime: "automatic",
    }),
  ],
  build: {
    manifest: true,
  },
  preview: {
    proxy: {
      "/api": apiProxyTarget,
    },
  },
});
