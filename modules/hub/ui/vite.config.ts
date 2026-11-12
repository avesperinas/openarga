import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "hub", dir: import.meta.dirname, port: 5177, apiPort: 8041 }));
