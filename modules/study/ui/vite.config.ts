import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "study", dir: import.meta.dirname, port: 5183, apiPort: 8036 }));
