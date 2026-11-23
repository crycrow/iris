import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "frappe-gantt-style": fileURLToPath(
        new URL(
          "./node_modules/frappe-gantt/dist/frappe-gantt.css",
          import.meta.url,
        ),
      ),
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { chunkSizeWarningLimit: 700 },
});
