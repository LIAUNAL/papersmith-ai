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
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    // Fonts stay files: the server's CSP has no font-src, so a font inlined as data: would be blocked.
    assetsInlineLimit: (file: string) => (/\.(woff2?|ttf|otf|eot)$/.test(file) ? false : undefined),
    // Every npm package the app bundles, with its licence text; PaperSmith ships it in its wheel.
    license: { fileName: "THIRD_PARTY_NOTICES.md" },
    rolldownOptions: {
      output: {
        // The libraries the editor loads up front, each in its own chunk instead of one 1 MB entry: the same code,
        // loaded at the same time, but in files the browser caches apart from the app's. pdf.js already loads
        // on demand (src/preview/engine-pdfjs.ts) and stays in its own chunk.
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            { name: "codemirror", test: /node_modules[\\/](@codemirror|@lezer|@marijn|crelt|style-mod|w3c-keyname)[\\/]/ },
            { name: "katex", test: /node_modules[\\/]katex[\\/]/ },
          ],
        },
      },
    },
  },
  server: { proxy: { "/api": { target: `http://127.0.0.1:${DEV_PORT}`, changeOrigin: true } } },
});
