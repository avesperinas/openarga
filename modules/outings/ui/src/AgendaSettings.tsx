import { Button, ConfirmDelete, Hint, List, ListRow, OfflineNotice, Section, TextField } from "@openarga/ui";
import { useState } from "react";

import {
  type Interest,
  type PluggedSource,
  addInterest,
  readInterests,
  readSources,
  removeInterest,
  unplugSource,
} from "./api";
import { t } from "./lang";
import { Pending, changed, useLoad } from "./Loads";
import { UpdateSheet } from "./UpdateSheet";
import { since } from "./words";

export function AgendaSettings() {
  const plugged = useLoad("sources", readSources).data?.plugged ?? [];
  const { data: interests, found } = useLoad("interests", readInterests);
  const [liked, setLiked] = useState("");
  const [muted, setMuted] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [removing, setRemoving] = useState<PluggedSource | null>(null);
  const [updating, setUpdating] = useState(false);

  const refresh = changed;

  async function add(kind: Interest["kind"], term: string) {
    if (term.trim().length < 2) return;
    setProblem(null);
    try {
      await addInterest(kind, term.trim());
      if (kind === "like") setLiked("");
      else setMuted("");
      refresh();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("problem.save"));
    }
  }

  async function remove(one: Interest) {
    try {
      await removeInterest(one.id);
      refresh();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("problem.remove"));
    }
  }

  const of = (kind: Interest["kind"]) => (interests ?? []).filter((one) => one.kind === kind);

  return (
    <>
      <OfflineNotice />
      <Section title={t("tab.agenda")}>
        <Hint>{t("settings.agenda_hint")}</Hint>
        <Button variant="secondary" icon="copy" onClick={() => setUpdating(true)}>
          {t("settings.update")}
        </Button>
        {plugged.length > 0 && (
          <>
            <Hint tone="warning">{t("settings.plugged_warning")}</Hint>
            <List>
              {plugged.map((source) => (
                <ListRow
                  key={source.connection}
                  title={source.label}
                  subtitle={source.last_run_at ? t("settings.read", { when: since(source.last_run_at) }) : undefined}
                  tone="warning"
                  icon="calendar"
                  hue={5}
                  action={{ icon: "trash", label: t("action.remove_named", { name: source.label }), onClick: () => setRemoving(source) }}
                />
              ))}
            </List>
          </>
        )}
      </Section>

      {interests === null && <Pending found={found} rows={3} />}

      <Section title={t("settings.likes")} count={of("like").length || undefined}>
        <Hint>{t("settings.likes_hint")}</Hint>
        {of("like").length > 0 && <Terms terms={of("like")} onRemove={(one) => void remove(one)} />}
        <TextField label={t("action.add")} value={liked} onChange={setLiked} onSubmit={() => void add("like", liked)} placeholder={t("settings.likes_placeholder")} />
        {liked.trim() && (
          <Button variant="secondary" icon="plus" onClick={() => void add("like", liked)}>
            {t("action.add")}
          </Button>
        )}
      </Section>

      <Section title={t("settings.mutes")} count={of("mute").length || undefined}>
        <Hint>{t("settings.mutes_hint")}</Hint>
        {of("mute").length > 0 && <Terms terms={of("mute")} onRemove={(one) => void remove(one)} />}
        <TextField label={t("action.mute")} value={muted} onChange={setMuted} onSubmit={() => void add("mute", muted)} placeholder={t("settings.mutes_placeholder")} />
        {muted.trim() && (
          <Button variant="secondary" icon="plus" onClick={() => void add("mute", muted)}>
            {t("action.mute")}
          </Button>
        )}
      </Section>

      {problem && <Hint tone="warning">{problem}</Hint>}

      {updating && <UpdateSheet onClose={() => setUpdating(false)} />}

      {removing && (
        <ConfirmDelete
          title={t("settings.unplug_title")}
          subject={removing.label}
          consequence={t("settings.unplug_consequence")}
          action={t("settings.unplug_action")}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await unplugSource(removing.connection);
            setRemoving(null);
            refresh();
          }}
        />
      )}
    </>
  );
}

function Terms({ terms, onRemove }: { terms: Interest[]; onRemove: (one: Interest) => void }) {
  return (
    <List>
      {terms.map((one) => (
        <ListRow
          key={one.id}
          title={one.term}
          icon={one.kind === "like" ? "heart" : "eye-off"}
          hue={one.kind === "like" ? 7 : 8}
          action={{ icon: "close", label: t("action.remove_named", { name: one.term }), onClick: () => onRemove(one) }}
        />
      ))}
    </List>
  );
}
