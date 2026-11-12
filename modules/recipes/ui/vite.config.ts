import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "recipes", dir: import.meta.dirname, port: 5175, apiPort: 8030 }));
