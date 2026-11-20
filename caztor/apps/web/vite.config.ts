import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const PLACEHOLDER = "__CAZTOR_TOKEN__";
const DEV_PORT = Number(process.env["CAZTOR_PORT"] ?? 4317);

/** Development only: the dev script passes the run's token in `CAZTOR_TOKEN` (with `CAZTOR_DEV=1`), like the server does. */
function devToken(): Plugin {
  return {
    name: "caztor-dev-token",
    apply: "serve",
    transformIndexHtml: (html) => {
      const token = process.env["CAZTOR_DEV"] === "1" ? process.env["CAZTOR_TOKEN"] : undefined;
      return token === undefined ? html : html.replaceAll(PLACEHOLDER, () => token);
    },
  };
}

export default defineConfig({
  plugins: [react(), devToken()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  server: { proxy: { "/api": { target: `http://127.0.0.1:${DEV_PORT}`, changeOrigin: true } } },
});
