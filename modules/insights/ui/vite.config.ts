import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "insights", dir: import.meta.dirname, port: 5194, apiPort: 8053 }));
