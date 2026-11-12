#!/usr/bin/env node
/* global process, console, URL */

import { mkdir, readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

import { chromium } from "playwright-core";

const [, , root, out] = process.argv;
if (!root || !out) {
  console.error("uso: shots.mjs <storybook-static> <salida>");
  process.exit(2);
}

const TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".png": "image/png",
};

const server = createServer(async (request, response) => {
  const path = normalize(decodeURIComponent(new URL(request.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  try {
    const body = await readFile(join(root, path.endsWith("/") ? `${path}index.html` : path));
    response.writeHead(200, { "content-type": TYPES[extname(path)] ?? "application/octet-stream" });
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;

const index = JSON.parse(await readFile(join(root, "index.json"), "utf8"));
const stories = Object.values(index.entries).filter((entry) => entry.type === "story");
await mkdir(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
let errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => message.type() === "error" && !message.text().startsWith("Failed to load resource") && errors.push(message.text()));
page.on("response", (response) => response.status() >= 400 && errors.push(`${response.status()} ${new URL(response.url()).pathname}`));

const failed = [];
for (const story of stories) {
  for (const theme of ["light", "dark"]) {
    errors = [];
    const name = `${story.id}--${theme}`;
    try {
      await page.goto(`${base}/iframe.html?id=${story.id}&viewMode=story&globals=theme:${theme}`, { waitUntil: "networkidle" });
      await page.waitForSelector("#storybook-root > *", { timeout: 10_000 });
      await page.waitForTimeout(400);
      await page.screenshot({ path: join(out, `${name}.png`), fullPage: true });
    } catch (error) {
      errors.push(error instanceof Error ? error.message.split("\n")[0] : String(error));
    }
    if (errors.length) failed.push({ name, errors });
  }
}

await browser.close();
server.close();

console.log(`capturas: ${stories.length} historia(s) × 2 temas en ${out}`);
if (failed.length) {
  for (const { name, errors: found } of failed) console.error(`  ${name}: ${found.join(" | ")}`);
  console.error(`${failed.length} captura(s) con error`);
  process.exit(1);
}
