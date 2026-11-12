import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(
  appConfig({ id: "goals", api: "goals", dir: import.meta.dirname, port: 5187, apiPort: 8047 }),
);
