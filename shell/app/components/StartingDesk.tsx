"use client";

import { Button, Hint, Section } from "@openarga/ui";
import * as React from "react";

import type { DesktopLayout, Device } from "../lib/kernel";
import { request } from "../lib/session";
import { currentDevice } from "./Editable";
import { say } from "../words";

const DESKTOPS = "/api/kernel/ui/desktops";

type State = "idle" | "asking" | "working" | "failed";


export function StartingDesk({ reload = () => globalThis.location.reload() }: { reload?: () => void }) {
  const [state, setState] = React.useState<State>("idle");
  const [device, setDevice] = React.useState<Device>("mobile");

  React.useEffect(() => setDevice(currentDevice()), []);

  const replace = async () => {
    setState("working");
    try {
      const [starting, current] = await Promise.all(
        [`${DESKTOPS}/starting`, DESKTOPS].map(async (url) => {
          const response = await request(url, { headers: { accept: "application/json" } });
          if (!response.ok) throw new Error(`${url} answered ${response.status}`);
          return (await response.json()) as Record<Device, DesktopLayout>;
        }),
      );
      const proposed = starting![device];
      const written = await request(`${DESKTOPS}/${device}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          pages: proposed.pages,
          placements: {},
          updated_at: current![device].updated_at ?? null,
        }),
      });
      if (!written.ok) throw new Error(`the desktop answered ${written.status}`);
      reload();
    } catch {
      setState("failed");
    }
  };

  return (
    <Section title={say("starting.title")}>
      <Hint>{say("starting.hint")}</Hint>
      {state === "asking" || state === "working" ? (
        <>
          <Hint>{say(`starting.confirm.${device}`)}</Hint>
          <div className="settings-actions">
            <Button variant="destructive" disabled={state === "working"} onClick={replace}>
              {say("starting.replace")}
            </Button>
            <Button disabled={state === "working"} onClick={() => setState("idle")}>
              {say("screens.cancel")}
            </Button>
          </div>
        </>
      ) : (
        <div className="settings-actions">
          <Button icon="undo" onClick={() => setState("asking")}>
            {say(`starting.use.${device}`)}
          </Button>
        </div>
      )}
      {state === "failed" && <Hint>{say("starting.failed")}</Hint>}
    </Section>
  );
}
