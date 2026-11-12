import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "training", dir: import.meta.dirname, port: 5173, apiPort: 8020 }));
