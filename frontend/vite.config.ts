import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget = env.FRONTEND_PROXY_TARGET || "http://backend:8000";
  const publicApiBaseUrl = env.FRONTEND_API_BASE_URL || "/api/v1";
  const publicWsBaseUrl = env.FRONTEND_WS_BASE_URL || "/ws/v1/chat";

  return {
    plugins: [react()],
    test: {
      environment: "node",
      globals: false,
      include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    },
    server: {
      host: "0.0.0.0",
      port: Number(env.FRONTEND_PORT || 3000),
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/ws": {
          target: backendTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    define: {
      __API_BASE_URL__: JSON.stringify(publicApiBaseUrl),
      __WS_BASE_URL__: JSON.stringify(publicWsBaseUrl),
    },
  };
});
