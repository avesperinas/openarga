import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "shopping", dir: import.meta.dirname, port: 5178, apiPort: 8031 }));
