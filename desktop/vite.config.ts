import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, target: "chrome128", sourcemap: false, chunkSizeWarningLimit: 900 },
  server: { port: 5173, strictPort: true, host: "127.0.0.1" },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
} as any);
