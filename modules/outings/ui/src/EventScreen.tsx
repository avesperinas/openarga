import { Button, Card, ChoiceChips, Hint, List, ListRow, OfflineNotice, Screen, Section } from "@openarga/ui";
import { useCallback, useState } from "react";

import {
  type Kind,
  type Near,
  Unauthorised,
  addInterest,
  dismissEvent,
  readEvent,
  readNear,
  saveEvent,
  signIn,
  splitEvent,
  toCalendar,
} from "./api";
import { ScreenHeader } from "./Header";
import { intl, t } from "./lang";
import { Pending, useLoad } from "./Loads";
import { MiniMap } from "./MiniMap";
import { categoryOf, kindOf, kinds, shortDay, since, span } from "./words";

export function EventScreen({
  id,
  backLabel,
  onBack,
  onWish,
}: {
  id: string;
  backLabel?: string;
  onBack: () => void;
  onWish: (id: string) => void;
}) {
  const { data: event, set: setEvent, found } = useLoad(`event:${id}`, () => readEvent(id));
  const near = useLoad(`near:${id}`, () => readNear(id)).data ?? [];
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : t("problem.save"));
  }, []);

  async function fancy() {
    if (!event) return;
    if (event.wish_id) return onWish(event.wish_id);
    setBusy(true);
    try {
      const wish = await saveEvent(event.id);
      setEvent({ ...event, wish_id: wish.id });
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function calendar() {
    if (!event) return;
    setBusy(true);
    try {
      setEvent(await toCalendar(event.id, !event.in_calendar));
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function separate(source: string) {
    if (!event) return;
    setBusy(true);
    try {
      await splitEvent(event.id, source);
      setEvent(await readEvent(event.id));
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function dismiss(on: boolean) {
    if (!event) return;
    setBusy(true);
    try {
      setEvent(await dismissEvent(event.id, on));
      setSaid(on ? t("event.dismissed_said") : "");
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function mute(term: string) {
    setBusy(true);
    try {
      await addInterest("mute", term);
      setSaid(t("event.muted_said", { term }));
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  const back = { label: backLabel ?? t("tab.agenda"), onClick: onBack };
  if (!event) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <OfflineNotice />
        <Pending found={found} />
      </Screen>
    );
  }

  const category = categoryOf(event.category);
  const where = [event.venue, event.town].filter(Boolean);
  const first = event.links[0];

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={`${category.label} · ${span(event)}${event.time ? ` · ${event.time}` : ""}`} title={event.title} />

      <OfflineNotice />

      <div className="outings-actions outings-actions-wide">
        <Button variant={event.wish_id ? "secondary" : "primary"} icon={event.wish_id ? "done" : "heart"} onClick={() => void fancy()} disabled={busy}>
          {event.wish_id ? t("event.in_wishes") : t("event.want")}
        </Button>
        <Button variant="secondary" icon={event.in_calendar ? "done" : "calendar"} onClick={() => void calendar()} disabled={busy}>
          {event.in_calendar ? t("event.in_planner") : t("event.to_planner")}
        </Button>
      </div>

      {problem && <Hint tone="warning">{problem}</Hint>}
      {event.dismissed && <Hint tone="warning">{t("event.dismissed")}</Hint>}
      {event.summary && <p className="outings-body outings-muted">{event.summary}</p>}

      {event.programme.length > 0 && (
        <Section title={t("event.programme")} count={event.programme.length}>
          <List>
            {event.programme.map((act) => (
              <ListRow key={act} title={act} icon={category.icon} hue={category.hue} />
            ))}
          </List>
        </Section>
      )}

      {where.length > 0 && (
        <Card flush>
          {event.lat != null && event.lon != null && (
            <MiniMap point={{ id: event.id, lon: event.lon, lat: event.lat, kind: "pill", label: shortDay(event.starts_on), hue: category.hue, title: event.title }} label={t("event.where", { place: where.join(", ") })} />
          )}
          <List>
            <ListRow title={where[0]!} subtitle={where[1] ?? undefined} icon="pin" hue={category.hue} />
          </List>
        </Card>
      )}

      {near.length > 0 && <NearWishes near={near} onWish={onWish} />}

      {event.links.length > 0 && (
        <Section title={event.links.length > 1 ? t("event.joined") : undefined}>
          <List>
            {event.links.map((link) => {
              const source = event.sources?.find((one) => one.page === link.page);
              const several = (event.sources?.length ?? 0) > 1;
              return (
                <ListRow
                  key={link.url}
                  title={link.name || new URL(link.page).host}
                  subtitle={several ? t("event.see_page_split") : t("event.see_page")}
                  icon="external"
                  hue={category.hue}
                  onClick={() => window.open(link.url, "_blank", "noopener")}
                  action={
                    several && source
                      ? { icon: "close", label: t("event.split", { name: link.name }), onClick: () => void separate(source.id) }
                      : undefined
                  }
                />
              );
            })}
          </List>
        </Section>
      )}

      <Section title={t("event.not_interested_title")}>
        <div className="outings-actions">
          <Button variant="plain" icon={event.dismissed ? "undo" : "eye-off"} onClick={() => void dismiss(!event.dismissed)} disabled={busy}>
            {event.dismissed ? t("event.restore") : t("settings.mutes")}
          </Button>
          {event.venue && !event.dismissed && (
            <Button variant="plain" icon="eye-off" onClick={() => void mute(event.venue!)} disabled={busy}>
              {t("event.nothing_at", { venue: event.venue })}
            </Button>
          )}
        </div>
        {said && <Hint>{said}</Hint>}
      </Section>

      <Hint>
        {first?.name ? t("event.arrived_from", { name: first.name, when: since(event.first_seen) }) : t("event.arrived", { when: since(event.first_seen) })}
      </Hint>
    </Screen>
  );
}

export function nearDefault(near: Near[]): Kind | null {
  return kinds().find((kind) => kind.value !== "eat" && near.some((one) => one.kind === kind.value))?.value ?? null;
}

function NearWishes({ near, onWish }: { near: Near[]; onWish: (id: string) => void }) {
  const [chosen, setChosen] = useState<Kind | "none" | null>(null);
  const present = kinds().filter((kind) => near.some((one) => one.kind === kind.value));
  const shown = chosen === "none" ? null : (chosen ?? nearDefault(near));
  const those = shown ? near.filter((one) => one.kind === shown) : [];
  return (
    <Section title={t("event.near_wishes")}>
      <ChoiceChips
        label={t("event.near_wishes_label")}
        scroll
        options={present.map((kind) => ({
          value: kind.value,
          label: `${kind.plural} ${near.filter((one) => one.kind === kind.value).length}`,
        }))}
        value={shown}
        onChange={(kind) => setChosen(kind === shown ? "none" : kind)}
      />
      {those.length > 0 && (
        <List>
          {those.map((one) => (
            <ListRow
              key={one.id}
              title={one.name}
              subtitle={t("event.near_km", { km: new Intl.NumberFormat(intl()).format(one.km) })}
              icon={kindOf(one.kind).icon}
              hue={kindOf(one.kind).hue}
              accessory="chevron-right"
              onClick={() => onWish(one.id)}
            />
          ))}
        </List>
      )}
    </Section>
  );
}
