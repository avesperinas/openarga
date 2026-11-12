import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

export default defineConfig(appConfig({ id: "notebook", dir: import.meta.dirname, port: 5188, apiPort: 8047 }));
