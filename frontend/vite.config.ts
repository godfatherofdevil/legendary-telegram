import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: Number(env.FRONTEND_PORT || 3000),
    },
    define: {
      __API_BASE_URL__: JSON.stringify(env.FRONTEND_API_BASE_URL || "http://localhost:8000/api/v1"),
      __WS_BASE_URL__: JSON.stringify(env.FRONTEND_WS_BASE_URL || "ws://localhost:8000/ws/v1/chat"),
    },
  };
});
