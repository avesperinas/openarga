import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export function assetVersion(file: string): string {
  const body = readFileSync(new URL(`./public/${file}`, import.meta.url));
  return createHash("sha256").update(body).digest("hex").slice(0, 10);
}

export const VERSIONED = ["icon.svg", "apple-touch-icon.png", "manifest.webmanifest"];

export const iconUrl = () => `/vitals/icon.svg?v=${assetVersion("icon.svg")}`;
