import { appTestConfig } from "@openarga/app/vite";
import { defineConfig } from "vitest/config";

export default defineConfig(appTestConfig({ id: "vitals", dir: import.meta.dirname }));
