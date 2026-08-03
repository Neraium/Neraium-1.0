import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config.js";

const webServer = Array.isArray(baseConfig.webServer)
  ? baseConfig.webServer.map((server, index) => index === 1
    ? {
        ...server,
        env: {
          ...server.env,
          VITE_PREFER_STORED_UPLOAD: "false",
        },
      }
    : server)
  : baseConfig.webServer;

export default defineConfig({
  ...baseConfig,
  webServer,
});
