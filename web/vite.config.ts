import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const contentSecurityPolicy = readFileSync(new URL("./public/_headers", import.meta.url), "utf8").match(/^  Content-Security-Policy: (.+)$/m)![1];

export default defineConfig({
  plugins: [react()],
  resolve: { conditions: ["onnxruntime-web-use-extern-wasm", "module", "browser", "development|production"] },
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) {
            return "react";
          }
        },
      },
    },
  },
  server: {
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
  preview: {
    headers: {
      "Content-Security-Policy": contentSecurityPolicy,
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
});
