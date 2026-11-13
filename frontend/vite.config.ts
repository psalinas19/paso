/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    // Precaches the whole app shell so the installed PWA opens in airplane mode.
    VitePWA({
      // "prompt" and we never prompt: a new version waits until the app is closed and
      // takes over on the next launch. "autoUpdate" reloads the page mid-use, which
      // would interrupt writing or wipe a half-typed name.
      registerType: "prompt",
      includeAssets: ["apple-touch-icon.png"],
      manifest: {
        name: "Paso",
        short_name: "Paso",
        description: "Libreta para iPad que revisa desarrollos de ingeniería",
        lang: "es",
        display: "standalone",
        background_color: "#e9e6df",
        theme_color: "#e9e6df",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
    }),
  ],
  test: { environment: "node" },
});
