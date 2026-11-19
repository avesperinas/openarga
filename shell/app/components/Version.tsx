"use client";

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
