import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { codeInspectorPlugin } from "code-inspector-plugin";

const backend = "http://localhost:8000";
export default defineConfig({
  plugins: [
    codeInspectorPlugin({ bundler: "vite" }),
    react(),
  ],
  server: {
    proxy: Object.fromEntries(
      // 后半截是 .scratch/ledgersage-frontend/missing-endpoints.md 里还没实现的端点，先把代理挂好。
      [
        "/auth",
        "/chat",
        "/dashboard",
        "/runs",
        "/accounts",
        "/transactions",
        "/admin",
        "/ledger",
        "/sessions",
        "/statements",
        "/analytics",
        "/saved-queries",
        "/reports",
        "/suggestions",
        "/events",
      ].map((path) => [path, backend]),
    ),
  },
});
