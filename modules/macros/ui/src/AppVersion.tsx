import { useResource } from "@openarga/app";
import { VersionTag } from "@openarga/ui";

import { readVersion } from "./api";

export function AppVersion() {
  const version = useResource("version", readVersion, { staleMs: Infinity }).data;
  if (!version) return null;
  return <VersionTag name="macros" version={version} />;
}
