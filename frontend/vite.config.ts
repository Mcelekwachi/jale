import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    tailwindcss(),
    VitePWA({
      registerType: "prompt",
      includeAssets: ["icon.svg", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"],
      manifest: {
        name: "Jalɛ",
        short_name: "Jalɛ",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
        background_color: "#f7f0df",
        theme_color: "#25214f",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,woff,woff2,svg,png,ico}"],
        runtimeCaching: [
          {
            urlPattern: ({ url, request }) =>
              request.method === "GET" &&
              url.origin === "https://jale-api.onrender.com" &&
              url.pathname.startsWith("/v1/") &&
              url.pathname !== "/v1/me" &&
              url.pathname !== "/v1/me/stats" &&
              !url.pathname.includes("/auth"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 200, maxAgeSeconds: 24 * 60 * 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ request, url }) =>
              request.method === "GET" &&
              (request.destination === "audio" || /\.(?:mp3|m4a|ogg|wav)$/i.test(url.pathname)),
            handler: "CacheFirst",
            options: {
              cacheName: "audio-cache",
              expiration: { maxEntries: 200, maxAgeSeconds: 30 * 24 * 60 * 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    restoreMocks: true,
  },
});
