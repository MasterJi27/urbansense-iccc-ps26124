import { copyFileSync, existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const here = dirname(fileURLToPath(import.meta.url));

function copyFieldAssets() {
  const ortSrc = join(here, "node_modules", "onnxruntime-web", "dist");
  const ortDest = join(here, "public", "ort");
  mkdirSync(ortDest, { recursive: true });
  if (existsSync(ortSrc)) {
    for (const f of readdirSync(ortSrc)) {
      if (f.endsWith(".wasm") || f.endsWith(".mjs") || (f.endsWith(".js") && f.includes("wasm"))) {
        copyFileSync(join(ortSrc, f), join(ortDest, f));
      }
    }
  }
  const weightsDest = join(here, "public", "weights");
  mkdirSync(weightsDest, { recursive: true });
  const webRdd = join(weightsDest, "rdd_web.onnx");
  const cloudRdd = join(here, "..", "backend", "app", "weights", "rdd_india.onnx");
  if (!existsSync(webRdd) && existsSync(cloudRdd)) {
    copyFileSync(cloudRdd, webRdd);
  }
  const manifestPath = join(weightsDest, "manifest.json");
  if (!existsSync(manifestPath)) {
    writeFileSync(
      manifestPath,
      JSON.stringify({
        rdd: { file: "rdd_web.onnx", imgsz: 640, honesty: "on-device preview of India RDD family — not a new test mAP" },
        person: { file: null, imgsz: 320, enabled: false },
      }),
    );
  }
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "copy-field-assets",
      buildStart: copyFieldAssets,
      configureServer() {
        copyFieldAssets();
      },
    },
  ],
  optimizeDeps: {
    exclude: ["onnxruntime-web"],
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
    watch: {
      ignored: ["**/public/ort/**", "**/public/weights/**"],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/maps": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  build: {
    assetsDir: "ui",
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          leaflet: ["leaflet", "react-leaflet"],
          charts: ["recharts"],
        },
      },
    },
  },
});
