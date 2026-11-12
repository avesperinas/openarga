import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "planner", dir: import.meta.dirname, port: 5186, apiPort: 8046 }));
