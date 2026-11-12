import { appTestConfig } from "@openarga/app/vite";
import { defineConfig } from "vitest/config";

export default defineConfig(appTestConfig({ id: "shopping", dir: import.meta.dirname }));
