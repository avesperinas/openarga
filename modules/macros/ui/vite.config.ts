import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "macros", dir: import.meta.dirname, port: 5191, apiPort: 8051 }));
