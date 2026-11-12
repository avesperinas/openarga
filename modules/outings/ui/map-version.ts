import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

export function mapVersion(dir: string): string {
  const root = join(dir, "public", "map");
  const hash = createHash("sha256");
  const visit = (folder: string) => {
    const entries = readdirSync(folder, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1));
    for (const entry of entries) {
      const full = join(folder, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.name !== "VERSION") hash.update(relative(root, full)).update("\0").update(readFileSync(full));
    }
  };
  visit(root);
  return hash.digest("hex").slice(0, 12);
}
