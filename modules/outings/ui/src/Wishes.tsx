import {
  CreateButton,
  EmptyState,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  PhotoTile,
  Screen,
  Section,
  SegmentedControl,
  Tiles,
} from "@openarga/ui";
import { mutate } from "@openarga/app";
import { useCallback, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Planned,
  type Wish,
  Unauthorised,
  markDone,
  photoUrl,
  readPlanned,
  readWishes,
  restoreWish,
  signIn,
} from "./api";
import { ScreenHeader } from "./Header";
import { Pending, changed, useLoad } from "./Loads";
import { WishSheet } from "./WishSheet";
import {
  NEW_KIND,
  PLANNED_PHASE,
  WISH_TABS,
  type WishTab,
  cardLine,
  doneLine,
  groups,
  inTab,
  kindOf,
  plannedLine,
  wishLine,
} from "./words";

export function WishesScreen({ onOpen }: { onOpen: (wish: Wish) => void }) {
  const { data: wishes, found } = useLoad("wishes", () => readWishes());
  const { data: archive } = useLoad("wishes:archive", () => readWishes(true));
  const planned = useLoad("planned", readPlanned).data ?? [];
  const [showArchive, setShowArchive] = useState(false);
  const [tab, setTab] = useState<WishTab>(() => {
    try {
      const kept = window.localStorage.getItem("outings.wishes.tab");
      return WISH_TABS.some((one) => one.value === kept) ? (kept as WishTab) : "outings";
    } catch {
      return "outings";
    }
  });

  function choose(next: WishTab) {
    setTab(next);
    try {
      window.localStorage.setItem("outings.wishes.tab", next);
    } catch {
    }
  }
  const [adding, setAdding] = useState(false);
  const [problem, setProblem] = useState("");

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
  }, []);

  async function done(wish: Wish) {
    setProblem("");
    void mutate<Wish[]>("wishes", (wishes ?? []).filter((one) => one.id !== wish.id));
    try {
      await markDone(wish.id);
    } catch (error) {
      fail(error);
    }
    changed();
  }

  async function restore(wish: Wish) {
    setProblem("");
    try {
      await restoreWish(wish.id);
    } catch (error) {
      fail(error);
    }
    changed();
  }

  const shown = groups(wishes ?? [], tab);
  const archived = (archive ?? []).filter((one) => inTab(one, tab));

  return (
    <Screen>
      <ScreenHeader eyebrow="Lo que nos apetece" title="Ganas" />

      <SegmentedControl label="Tipo" options={WISH_TABS} value={tab} onChange={choose} />

      <OfflineNotice />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {wishes === null && <Pending found={found} rows={4} />}

      {wishes !== null && wishes.length === 0 && (
        <EmptyState icon="bookmark" title="Nada apuntado todavía" action={{ label: "Apuntar", onClick: () => setAdding(true) }}>
          Una escapada, un restaurante o un viaje: con una foto, su nombre y dónde está.
        </EmptyState>
      )}
      {wishes !== null && wishes.length > 0 && shown.length === 0 && <Hint>Nada aquí por ahora.</Hint>}

      {tab === "trips" && planned.length > 0 && (
        <Section title="Planeando" count={planned.length}>
          <Tiles label="Planeando">
            {planned.map((one) => (
              <PlannedCard key={`${one.app}-${one.id}`} trip={one} />
            ))}
          </Tiles>
        </Section>
      )}

      {shown.map((group) => (
        <Section key={group.id} title={group.title} count={group.wishes.length}>
          {group.layout === "cards" ? (
            <Tiles label={group.title}>
              {group.wishes.map((wish) => (
                <WishCard key={wish.id} wish={wish} onOpen={() => onOpen(wish)} />
              ))}
            </Tiles>
          ) : (
            <List>
              {group.wishes.map((wish) => (
                <ListRow
                  key={wish.id}
                  title={wish.name}
                  subtitle={wishLine(wish)}
                  image={photoUrl(wish, "thumb")}
                  icon={wish.has_photo ? undefined : kindOf(wish.kind).icon}
                  hue={kindOf(wish.kind).hue}
                  onClick={() => onOpen(wish)}
                  action={{ icon: "done", label: "Hecho", kind: "check", onClick: () => void done(wish) }}
                />
              ))}
            </List>
          )}
        </Section>
      ))}

      {archived.length > 0 && (
        <Section
          title="Archivo"
          count={archived.length}
          action={{ label: showArchive ? "Ocultar" : "Ver", onClick: () => setShowArchive(!showArchive) }}
        >
          {showArchive && (
            <List>
              {archived.map((wish) => (
                <ListRow
                  key={wish.id}
                  title={wish.name}
                  subtitle={doneLine(wish)}
                  image={photoUrl(wish, "thumb")}
                  icon={wish.has_photo ? undefined : kindOf(wish.kind).icon}
                  hue={kindOf(wish.kind).hue}
                  onClick={() => onOpen(wish)}
                  action={{ icon: "undo", label: "Devolver a la lista", onClick: () => void restore(wish) }}
                />
              ))}
            </List>
          )}
        </Section>
      )}

      <AppVersion />

      <CreateButton label="Apuntar" onClick={() => setAdding(true)} />

      {adding && (
        <WishSheet
          initialKind={NEW_KIND[tab]}
          onClose={() => setAdding(false)}
          onSaved={(wish) => {
            setAdding(false);
            setProblem("");
            changed();
            onOpen(wish);
          }}
          onError={fail}
        />
      )}
    </Screen>
  );
}

export function WishCard({ wish, onOpen }: { wish: Wish; onOpen: () => void }) {
  const kind = kindOf(wish.kind);
  return (
    <PhotoTile
      title={wish.name}
      detail={cardLine(wish) || undefined}
      src={photoUrl(wish, "thumb")}
      hue={kind.hue}
      icon={kind.icon}
      onOpen={onOpen}
    />
  );
}

export function PlannedCard({ trip }: { trip: Planned }) {
  return (
    <PhotoTile
      title={trip.title}
      detail={plannedLine(trip) || undefined}
      src={trip.image}
      hue={5}
      icon="plane"
      badge={PLANNED_PHASE[trip.phase]}
      href={trip.href}
    />
  );
}
