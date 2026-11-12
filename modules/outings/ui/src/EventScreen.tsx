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
import { Pending, useLoad } from "./Loads";
import { MiniMap } from "./MiniMap";
import { KINDS, categoryOf, kindOf, shortDay, since, span } from "./words";

export function EventScreen({
  id,
  backLabel = "Agenda",
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
    setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
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
      setSaid(on ? "Apartado: ya no sale en Explorar ni en la Agenda." : "");
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
      setSaid(`Silenciado: nada de «${term}» saldrá en Explorar. Se deshace en Ajustes.`);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  const back = { label: backLabel, onClick: onBack };
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
          {event.wish_id ? "En Ganas" : "Me apetece"}
        </Button>
        <Button variant="secondary" icon={event.in_calendar ? "done" : "calendar"} onClick={() => void calendar()} disabled={busy}>
          {event.in_calendar ? "En Planner" : "A Planner"}
        </Button>
      </div>

      {problem && <Hint tone="warning">{problem}</Hint>}
      {event.dismissed && <Hint tone="warning">Apartado: no te interesa.</Hint>}
      {event.summary && <p className="outings-body outings-muted">{event.summary}</p>}

      {event.programme.length > 0 && (
        <Section title="Programa" count={event.programme.length}>
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
            <MiniMap point={{ id: event.id, lon: event.lon, lat: event.lat, kind: "pill", label: shortDay(event.starts_on), hue: category.hue, title: event.title }} label={`Dónde es: ${where.join(", ")}`} />
          )}
          <List>
            <ListRow title={where[0]!} subtitle={where[1] ?? undefined} icon="pin" hue={category.hue} />
          </List>
        </Card>
      )}

      {near.length > 0 && <NearWishes near={near} onWish={onWish} />}

      {event.links.length > 0 && (
        <Section title={event.links.length > 1 ? "Unido de varias agendas" : undefined}>
          <List>
            {event.links.map((link) => {
              const source = event.sources?.find((one) => one.page === link.page);
              const several = (event.sources?.length ?? 0) > 1;
              return (
                <ListRow
                  key={link.url}
                  title={link.name || new URL(link.page).host}
                  subtitle={several ? "Ver en su página · si no es el mismo, sepáralo" : "Ver en su página"}
                  icon="external"
                  hue={category.hue}
                  onClick={() => window.open(link.url, "_blank", "noopener")}
                  action={
                    several && source
                      ? { icon: "close", label: `Separar ${link.name}`, onClick: () => void separate(source.id) }
                      : undefined
                  }
                />
              );
            })}
          </List>
        </Section>
      )}

      <Section title="¿No te interesa?">
        <div className="outings-actions">
          <Button variant="plain" icon={event.dismissed ? "undo" : "eye-off"} onClick={() => void dismiss(!event.dismissed)} disabled={busy}>
            {event.dismissed ? "Devolverlo" : "No me interesa"}
          </Button>
          {event.venue && !event.dismissed && (
            <Button variant="plain" icon="eye-off" onClick={() => void mute(event.venue!)} disabled={busy}>
              Nada en {event.venue}
            </Button>
          )}
        </div>
        {said && <Hint>{said}</Hint>}
      </Section>

      <Hint>
        Llegó{first?.name ? ` de ${first.name}` : ""} · {since(event.first_seen)}
      </Hint>
    </Screen>
  );
}

export function nearDefault(near: Near[]): Kind | null {
  return KINDS.find((kind) => kind.value !== "eat" && near.some((one) => one.kind === kind.value))?.value ?? null;
}

function NearWishes({ near, onWish }: { near: Near[]; onWish: (id: string) => void }) {
  const [chosen, setChosen] = useState<Kind | "none" | null>(null);
  const kinds = KINDS.filter((kind) => near.some((one) => one.kind === kind.value));
  const shown = chosen === "none" ? null : (chosen ?? nearDefault(near));
  const those = shown ? near.filter((one) => one.kind === shown) : [];
  return (
    <Section title="Cerca, de tus ganas">
      <ChoiceChips
        label="Qué ganas cerca"
        scroll
        options={kinds.map((kind) => ({
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
              subtitle={`A ${String(one.km).replace(".", ",")} km · para aprovechar el viaje`}
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
