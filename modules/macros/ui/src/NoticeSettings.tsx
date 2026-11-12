import { Button, Card, Hint, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { readSettings, saveSettings } from "./api";

const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;

export function NoticeSettings() {
  const [at, setAt] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");

  useEffect(() => {
    void readSettings()
      .then((found) => setAt(found.protein_at.slice(0, 5)))
      .catch(() => setState("failed"));
  }, []);

  const valid = HHMM.test(at);
  const save = () => {
    if (!valid) return;
    setState("saving");
    void saveSettings(at)
      .then((found) => {
        setAt(found.protein_at.slice(0, 5));
        setState("saved");
      })
      .catch(() => setState("failed"));
  };

  return (
    <Card title="Aviso de proteína">
      <TextField
        label="A qué hora"
        type="time"
        value={at}
        onChange={(value) => {
          setAt(value);
          setState("idle");
        }}
        onSubmit={save}
        hint="Si a esa hora no llegas a tu objetivo de proteína, te avisa. Se enciende en Ajustes → Avisos de arga."
      />
      {state === "failed" && <Hint tone="warning">No se pudo guardar.</Hint>}
      <Button variant="primary" disabled={!valid || state === "saving"} onClick={save}>
        {state === "saved" ? "Guardado" : "Guardar"}
      </Button>
    </Card>
  );
}
