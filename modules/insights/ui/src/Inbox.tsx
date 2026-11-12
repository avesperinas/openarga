import { useResource } from "@openarga/app";
import {
  EmptyState,
  ErrorState,
  Hint,
  IconBadge,
  List,
  ListRow,
  MediaCard,
  OfflineNotice,
  Screen,
  Section,
  Skeleton,
} from "@openarga/ui";

import { AppVersion } from "./AppVersion";
import { INSIGHTS, type Insight, readInsights, readRuns, readSignals } from "./api";
import { ScreenHeader, useApp } from "./Header";
import { DOMAIN_HUES, DOMAIN_ICONS, DOMAINS, amount, changeOf, lastLook, when } from "./words";

export function sections(insights: Insight[]): { title: string; insights: Insight[] }[] {
  const unread = insights.filter((one) => one.read_at === null);
  const read = insights.filter((one) => one.read_at !== null);
  return [
    { title: "Sin leer", insights: unread },
    { title: "Leídos", insights: read },
  ].filter((section) => section.insights.length > 0);
}

export const origin = (insight: Insight) =>
  `${insight.kind === "weekly" ? "Tu semana" : DOMAINS[insight.domain]} · ${when(insight.created_at)}`;

export function headline(insight: Insight): string | null {
  const first = insight.figures[0];
  if (!first) return null;
  const change = changeOf(first);
  return `${first.label} ${amount(first.value, first.unit)}${change ? ` · ${change}` : ""}`;
}

export function InboxScreen({ onOpen, onSettings }: { onOpen: (id: string) => void; onSettings: () => void }) {
  const app = useApp();
  const found = useResource(INSIGHTS, readInsights, { persist: true });
  const signals = useResource("signals", readSignals).data ?? [];
  const runs = useResource("runs", readRuns).data;
  const insights = found.data ?? null;

  return (
    <Screen>
      <ScreenHeader title="Consejos" />
      <OfflineNotice />

      {runs !== undefined && <Hint>{lastLook(runs, app.name)}</Hint>}
      {found.loading && <Skeleton label="Cargando los consejos" />}
      {insights === null && found.error && (
        <ErrorState title="No se pudieron leer los consejos" detail={found.error.message} onRetry={found.refresh} />
      )}

      {insights !== null && insights.length === 0 && (
        <EmptyState
          title={`${app.name} todavía no te ha dicho nada`}
          action={{
            label: "Contarle qué te importa",
            icon: "spark",
            onClick: onSettings,
          }}
        >
          Mira tus datos y solo te escribe cuando algo se sale de lo tuyo: con tus cifras, lo que afecta y qué harías.
          Cuéntale en Ajustes qué te importa, y lo tendrá en cuenta.
        </EmptyState>
      )}

      {insights !== null &&
        sections(insights).map((section) =>
          section.title === "Sin leer" ? (
            <Section key={section.title} title="Sin leer" count={section.insights.length}>
              {section.insights.map((one) => (
                <MediaCard
                  key={one.id}
                  media={<IconBadge name={DOMAIN_ICONS[one.domain]} hue={DOMAIN_HUES[one.domain]} />}
                  title={one.title}
                  lines={[origin(one), headline(one)].filter((line): line is string => Boolean(line))}
                  onOpen={() => onOpen(one.id)}
                />
              ))}
            </Section>
          ) : (
            <Section key={section.title} title={section.title} count={section.insights.length}>
              <List>
                {section.insights.map((one) => (
                  <ListRow
                    key={one.id}
                    icon={DOMAIN_ICONS[one.domain]}
                    title={one.title}
                    subtitle={origin(one)}
                    accessory="chevron-right"
                    onClick={() => onOpen(one.id)}
                  />
                ))}
              </List>
            </Section>
          ),
        )}

      {signals.length > 0 && (
        <Section title="Lo que ve esta semana" count={signals.length}>
          <List>
            {signals.map((one) => (
              <ListRow
                key={one.id}
                icon={DOMAIN_ICONS[one.domain]}
                title={one.text}
                subtitle={`${DOMAINS[one.domain]} · ${when(one.day)}`}
              />
            ))}
          </List>
        </Section>
      )}

      <AppVersion />
    </Screen>
  );
}
