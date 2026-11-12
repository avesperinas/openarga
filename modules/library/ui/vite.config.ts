import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "library", dir: import.meta.dirname, port: 5181, apiPort: 8034 }));
