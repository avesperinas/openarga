import { VersionTag } from "@openarga/ui";
import { useEffect, useState } from "react";

import { readVersion } from "./api";

export function AppVersion() {
  const [version, setVersion] = useState("");
  useEffect(() => {
    void readVersion().then(setVersion);
  }, []);
  if (!version) return null;
  return <VersionTag name="goals" version={version} />;
}
