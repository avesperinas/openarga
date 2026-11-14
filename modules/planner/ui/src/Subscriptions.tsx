import {
  Button,
  EmptyState,
  ErrorState,
  GroupLabel,
  Hint,
  InletSettings,
  type InletValues,
  List,
  ListRow,
  Sheet,
  Skeleton,
  type SourceAnswers,
  SourceQuestions,
  Switch,
  inletValues,
  proposedSourceName,
  sourceMissing,
  sourceParams,
  useNow,
} from "@openarga/ui";
import * as React from "react";

import { type Layer, type Source, type SubscriptionMenu, readSubscriptionMenu, searchSource, subscribe, unsubscribe } from "./api";
import { statusLine } from "./Subscribe";
import { t } from "./lang";

interface Props {
  onClose: () => void;
  onSubscribed: (layer: Layer) => void;
  onUnsubscribed: (layer: Layer) => void;
}

export function SubscriptionsSheet({ onClose, onSubscribed, onUnsubscribed }: Props) {
  const [menu, setMenu] = React.useState<SubscriptionMenu | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [adding, setAdding] = React.useState<Source | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const now = useNow(60_000);

  const load = React.useCallback(
    () =>
      readSubscriptionMenu()
        .then((found) => {
          setMenu(found);
          setError(null);
        })
        .catch((failure: unknown) => setError(failure instanceof Error ? failure.message : String(failure))),
    [],
  );
  React.useEffect(() => {
    void load();
  }, [load]);

  const remove = async (layer: Layer) => {
    setBusy(layer.id);
    try {
      await unsubscribe(layer.id);
      setMenu((current) =>
        current && {
          ...current,
          sources: current.sources.map((one) => ({ ...one, subscribed: one.subscribed.filter((l) => l.id !== layer.id) })),
          others: current.others.filter((l) => l.id !== layer.id),
        },
      );
      onUnsubscribed(layer);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  };

  if (adding) {
    return (
      <SourceForm
        source={adding}
        onBack={() => setAdding(null)}
        onSubscribed={(layer) => {
          onSubscribed(layer);
          setAdding(null);
          void load();
        }}
      />
    );
  }

  const listed = menu?.groups ?? [];
  const groups = listed.map((group) => ({ ...group, sources: menu?.sources.filter((one) => one.group === group.id) ?? [] }));
  const known = new Set(listed.map((one) => one.id));
  const rest = menu?.sources.filter((one) => !known.has(one.group)) ?? [];
  if (rest.length) groups.push({ id: "rest", title: t("subs.more"), sources: rest });

  return (
    <Sheet title={t("subs.title")} onClose={onClose}>
      <div className="cr-subscribe">
        {error && menu && (
          <p className="cr-error" role="alert">
            {error}
          </p>
        )}
        {!menu && !error && <Skeleton rows={4} label={t("subs.loading")} />}
        {!menu && error && <ErrorState title={t("subs.hub_down")} detail={error} onRetry={load} />}
        {menu && menu.sources.length === 0 && menu.others.length === 0 && (
          <EmptyState
            icon="globe"
            title={t("subs.empty")}
            action={{ label: t("subs.to_hub"), icon: "chevron-right", onClick: () => window.location.assign("/hub") }}
          >
            {t("subs.empty_body")}
          </EmptyState>
        )}
        {groups
          .filter((group) => group.sources.length > 0)
          .map((group) => (
            <section key={group.id} className="cr-subscribe-field" aria-label={group.title}>
              <GroupLabel>{group.title}</GroupLabel>
              {group.sources.map((source) => (
                <SourceBlock
                  key={source.provider}
                  source={source}
                  now={now}
                  busy={busy}
                  onAdd={() => setAdding(source)}
                  onRemove={(layer) => void remove(layer)}
                />
              ))}
            </section>
          ))}
        {menu && menu.others.length > 0 && (
          <section className="cr-subscribe-field" aria-label="Desde Hub">
            <GroupLabel>Desde Hub</GroupLabel>
            <List>
              {menu.others.map((layer) => (
                <ListRow key={layer.id} title={layer.name} subtitle={statusLine(layer, now)} hue={layer.tone} />
              ))}
            </List>
          </section>
        )}
        <Hint>{t("subs.note")}</Hint>
      </div>
    </Sheet>
  );
}

function SourceBlock({
  source,
  now,
  busy,
  onAdd,
  onRemove,
}: {
  source: Source;
  now: number;
  busy: string | null;
  onAdd: () => void;
  onRemove: (layer: Layer) => void;
}) {
  const [only] = source.subscribed;
  if (!source.many) {
    return (
      <div className="cr-source">
        <div className="cr-source-head">
          <span className="cr-source-text">
            <span className="cr-source-title">{source.title}</span>
            <span className="cr-source-subtitle">{only ? statusLine(only, now) : source.subtitle}</span>
          </span>
          <Switch label={source.title} checked={!!only} disabled={busy !== null} onChange={(on) => (on ? onAdd() : only && onRemove(only))} />
        </div>
      </div>
    );
  }
  return (
    <div className="cr-source">
      <div className="cr-source-head">
        <span className="cr-source-text">
          <span className="cr-source-title">{source.title}</span>
          <span className="cr-source-subtitle">{source.subtitle}</span>
        </span>
        <Button size="small" variant="tinted" icon="plus" onClick={onAdd}>
          {t("action.add")}
        </Button>
      </div>
      {source.subscribed.length > 0 && (
        <List>
          {source.subscribed.map((layer) => (
            <ListRow
              key={layer.id}
              title={layer.name}
              subtitle={statusLine(layer, now)}
              hue={layer.tone}
              tone={layer.subscription?.failing ? "warning" : undefined}
              action={{ icon: "trash", label: t("action.remove_named", { name: layer.name }), onClick: () => onRemove(layer) }}
              disabled={busy === layer.id}
            />
          ))}
        </List>
      )}
    </div>
  );
}

function SourceForm({ source, onBack, onSubscribed }: { source: Source; onBack: () => void; onSubscribed: (layer: Layer) => void }) {
  const [answers, setAnswers] = React.useState<SourceAnswers>({});
  const [chosen, setChosen] = React.useState<InletValues>({});
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const inlet = source.inlets?.[0];
  const settings = (inlet?.settings?.length ? inlet.settings : fallback()).map(localised);
  const values = inletValues(settings, chosen, proposedSourceName(source, answers), source.tone);
  const search = React.useCallback(
    (ask: string, query?: string, parent?: string) => searchSource(source.provider, ask, query, parent),
    [source.provider],
  );

  const save = async () => {
    const lacks = sourceMissing(source.asks, answers);
    if (lacks) return setError(lacks);
    const name = String(values.name ?? "").trim();
    if (!name) return setError(t("form.no_name"));
    setBusy(true);
    setError(null);
    try {
      onSubscribed(await subscribe(source.provider, name, Number(values.tone ?? source.tone) as Layer["tone"], sourceParams(source.asks, answers)));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title={source.title} onClose={onBack} action={{ label: busy ? t("subs.subscribing") : t("subs.subscribe"), onClick: () => void save(), disabled: busy }}>
      <div className="cr-subscribe">
        <SourceQuestions asks={source.asks} answers={answers} onChange={setAnswers} search={search} onError={setError} />
        <InletSettings settings={settings} values={values} onChange={setChosen} />
        {error && (
          <p className="cr-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </Sheet>
  );
}

const LABELS: Record<string, string> = { name: "subs.layer_name", tone: "field.tone" };

const fallback = () => [
  { key: "name", kind: "text", label: "" },
  { key: "tone", kind: "tone", label: "" },
];

const localised = <T extends { key: string; label: string }>(setting: T): T => {
  const key = LABELS[setting.key];
  return key ? { ...setting, label: t(key) } : setting;
};
