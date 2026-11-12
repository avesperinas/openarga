import { Button, Hint, Sheet } from "@openarga/ui";
import { useState } from "react";

import { readAgendaPrompt } from "./api";
import { t } from "./lang";

export function UpdateSheet({ onClose }: { onClose: () => void }) {
  const [said, setSaid] = useState<{ tone?: "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function copy() {
    setBusy(true);
    try {
      const { prompt } = await readAgendaPrompt();
      await navigator.clipboard.writeText(prompt);
      setSaid({ text: t("update.copied") });
    } catch (error) {
      setSaid({ tone: "warning", text: error instanceof Error ? error.message : t("problem.copy") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet title={t("update.title")} onClose={onClose}>
      <div className="outings-fields">
        <Hint>{t("update.hint")}</Hint>
        <Button variant="primary" icon="copy" onClick={() => void copy()} disabled={busy}>
          {t("update.copy")}
        </Button>
        {said && <Hint tone={said.tone}>{said.text}</Hint>}
      </div>
    </Sheet>
  );
}
