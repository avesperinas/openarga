import { Button, Card, Hint, TextField, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { readSettings, saveSettings } from "./api";

const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;

export function NoticeSettings() {
  const t = useT();
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
    <Card title={t("notice.title")}>
      <TextField
        label={t("notice.at")}
        type="time"
        value={at}
        onChange={(value) => {
          setAt(value);
          setState("idle");
        }}
        onSubmit={save}
        hint={t("notice.hint")}
      />
      {state === "failed" && <Hint tone="warning">{t("common.save_failed")}</Hint>}
      <Button variant="primary" disabled={!valid || state === "saving"} onClick={save}>
        {state === "saved" ? t("common.saved") : t("common.save")}
      </Button>
    </Card>
  );
}
