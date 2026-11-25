import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    projects: [
      {
        test: {
          name: "node",
          environment: "node",
          include: [
            "packages/*/test/**/*.test.ts",
            "guides/**/*.test.ts",
            "apps/server-local/**/*.test.ts",
            "agents/**/*.test.ts",
          ],
          exclude: ["**/node_modules/**", "**/dist/**"],
        },
      },
      {
        plugins: [react()],
        test: {
          name: "jsdom",
          environment: "jsdom",
          setupFiles: ["apps/web/test/setup.ts"],
          include: ["apps/web/**/*.test.{ts,tsx}"],
          exclude: ["**/node_modules/**", "**/dist/**"],
        },
      },
    ],
  },
});
