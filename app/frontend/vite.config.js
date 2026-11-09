import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5500",
      "/static": "http://127.0.0.1:5500",
      "/ruffle": "http://127.0.0.1:5500",
      "/assets": "http://127.0.0.1:5500",
      "/preview.swf": "http://127.0.0.1:5500",
      "/anim_preview.swf": "http://127.0.0.1:5500",
      "/proxy.pac": "http://127.0.0.1:5500",
      "/mg-proxy.pac": "http://127.0.0.1:5500",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
