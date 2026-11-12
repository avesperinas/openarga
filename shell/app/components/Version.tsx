"use client";

import { VersionTag } from "@openarga/ui";
import * as React from "react";

export function usePlatformVersion(given?: string): string {
  const [version, setVersion] = React.useState(given ?? "");
  React.useEffect(() => {
    if (given) return;
    fetch("/version", { headers: { accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { version?: string } | null) => body?.version && setVersion(body.version))
      .catch(() => undefined);
  }, [given]);
  return version;
}

export function PlatformVersion({ version }: { version?: string }) {
  const shown = usePlatformVersion(version);
  if (!shown) return null;
  return (
    <div className="desktop-version">
      <VersionTag name="arga" version={shown} />
    </div>
  );
}
