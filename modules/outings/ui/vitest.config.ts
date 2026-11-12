import { appTestConfig } from "@openarga/app/vite";
import { defineConfig } from "vitest/config";

const base = appTestConfig({ id: "outings", dir: import.meta.dirname });

export default defineConfig({ ...base, define: { ...base.define, __OUTINGS_MAP__: JSON.stringify("test") } });
