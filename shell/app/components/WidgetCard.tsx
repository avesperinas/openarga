import {
  type AgendaEntry,
  type Hue,
  type IconName,
  Widget,
  WidgetAgenda,
  WidgetBars,
  WidgetCalendar,
  WidgetChart,
  WidgetFootnote,
  WidgetHeatmap,
  WidgetKpi,
  WidgetKpiDelta,
  WidgetProgress,
  WidgetList,
  WidgetRing,
  WidgetShortcuts,
  WidgetStats,
  WidgetStreak,
  WidgetTasks,
  WidgetUpNext,
  WidgetWeek,
} from "@openarga/ui";
import * as React from "react";

import type { CatalogueEntry, DeskItem, Envelope, EnvelopeBody, WidgetKind } from "../lib/kernel";

const CONNECTORS = "/hub";

const entriesOf = (body: EnvelopeBody): AgendaEntry[] | undefined =>
  body.entries?.map(({ all_day, ...entry }) => ({ ...entry, allDay: all_day }));

function Body({
  kind,
  body,
  hue,
  link,
  onAct,
}: {
  kind: WidgetKind;
  body: EnvelopeBody;
  hue: Hue;
  link?: string;
  onAct?: (verb: string, id: string) => Promise<boolean>;
}) {
  switch (kind) {
    case "kpi-delta":
      return (
        <WidgetKpiDelta
          value={body.value ?? 0}
          previous={body.previous ?? 0}
          unit={body.unit}
          detail={body.detail}
          since={body.since}
          goodWhen={body.good_when}
          series={body.series}
        />
      );

    case "chart":
      return (
        <WidgetChart
          series={body.series ?? []}
          value={body.value}
          unit={body.unit}
          detail={body.detail}
        />
      );

    case "bars":
      return (
        <WidgetBars
          series={body.series ?? []}
          labels={body.labels}
          value={body.value}
          unit={body.unit}
          detail={body.detail}
          highlight={body.highlight}
        />
      );

    case "heatmap":
      return (
        <WidgetHeatmap
          values={body.values ?? []}
          columns={body.columns}
          detail={body.detail}
        />
      );

    case "progress":
      return (
        <WidgetProgress
          value={Number(body.value ?? 0)}
          target={body.target ?? 0}
          unit={body.unit}
          label={body.label}
          expected={body.expected}
          goodWhen={body.good_when === "down" ? "down" : undefined}
        />
      );

    case "ring":
      return (
        <WidgetRing
          value={Number(body.value ?? 0)}
          target={body.target ?? 0}
          unit={body.unit}
          label={body.label}
          show={body.show}
          expected={body.expected}
        />
      );

    case "streak":
      return (
        <WidgetStreak
          current={body.current ?? Number(body.value ?? 0)}
          best={body.best}
          days={body.days}
          label={body.label}
        />
      );

    case "stats":
      return (
        <>
          <WidgetStats items={body.stats ?? []} />
          {body.detail && <WidgetFootnote>{body.detail}</WidgetFootnote>}
        </>
      );

    case "calendar":
      return (
        <WidgetCalendar marked={body.marked} today={body.today} entries={entriesOf(body)} />
      );

    case "tasks":
      return (
        <WidgetTasks
          tasks={body.tasks ?? []}
          count={body.count}
          onToggle={
            body.checkable && onAct
              ? (id, done) => onAct(done ? "complete" : "reopen", id)
              : undefined
          }
        />
      );

    case "agenda":
      return <WidgetAgenda entries={entriesOf(body) ?? []} />;

    case "week":
      return <WidgetWeek entries={entriesOf(body) ?? []} />;

    case "upnext":
      return <WidgetUpNext events={body.events ?? []} />;

    case "shortcuts":
      return (
        <WidgetShortcuts
          actions={(body.actions ?? []).map((action) => ({
            label: action.label,
            href: action.href,
            icon: action.icon as IconName | undefined,
          }))}
        />
      );

    case "list":
      return <WidgetList rows={body.rows ?? []} href={link} detail={body.detail} />;

    case "kpi":
    default:
      return (
        <WidgetKpi
          value={body.value ?? "—"}
          unit={body.unit}
          detail={body.detail}
          icon={body.icon as IconName | undefined}
          hue={(body.icon_hue as Hue | undefined) ?? hue}
        />
      );
  }
}

export function WidgetCard({
  item,
  entry,
  envelope,
  appIcon,
  link,
  onRetry,
  onAct,
}: {
  appIcon?: string;
  item: DeskItem;
  entry: CatalogueEntry | undefined;
  envelope: Envelope | null | undefined;
  link?: string;
  onRetry?: () => void;
  onAct?: (verb: string, id: string) => Promise<boolean>;
}) {
  if (!entry) return null;

  const state = envelope === undefined ? "loading" : (envelope?.state ?? "error");
  const body = envelope?.body ?? {};

  return (
    <Widget
      title={entry.title}
      hue={entry.hue as 1}
      appIcon={appIcon}
      size={item.size}
      shape={entry.shape}
      state={state}
      updatedAt={envelope ? new Date(envelope.updated_at) : undefined}
      note={state === "disconnected" || state === "empty" ? body.detail : undefined}
      onRetry={onRetry}
      onConnect={() => window.location.assign(CONNECTORS)}
      uncertainty={
        envelope?.uncertainty && {
          summary: envelope.uncertainty.summary,
          candidates: envelope.uncertainty.candidates?.map((candidate) => ({
            entityId: candidate.entity_id,
            label: candidate.label,
            weight: 1,
          })),
        }
      }
    >
      <Body kind={entry.kind} body={body} hue={entry.hue as Hue} link={link} onAct={onAct} />
    </Widget>
  );
}
