import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    restoreMocks: true,
  },
});
