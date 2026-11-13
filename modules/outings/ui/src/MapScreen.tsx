import { Button, Card, Hint, type IconName, List, ListRow, OfflineNotice, SegmentedControl } from "@openarga/ui";
import { AreaMap, type AreaPoint } from "@openarga/ui/area-map";
import { WorldMap } from "@openarga/ui/world-map";
import { useMemo, useState } from "react";

import { type Area, GEO_BASE, type MapPoints, type Zone, photoUrl, readMap } from "./api";
import { mapOf, useArea } from "./area";
import { t } from "./lang";
import { Pending, useLoad } from "./Loads";
import { categoryOf, kindOf, shortDay } from "./words";

type Scope = Zone | "world";

export const scopes = (area: Area | null): { value: Scope; label: string }[] => [
  ...(area?.map
    ? [
        { value: "near" as Scope, label: area.near },
        { value: "region" as Scope, label: area.region },
      ]
    : []),
  { value: "world", label: t("map.world") },
];

export function mapPoints(found: MapPoints): AreaPoint[] {
  return [
    ...found.events.map((event) => ({
      id: `event:${event.id}`,
      lon: event.lon,
      lat: event.lat,
      kind: "pill" as const,
      label: shortDay(event.starts_on),
      hue: categoryOf(event.category).hue,
      title: `${event.title}, ${shortDay(event.starts_on)}`,
    })),
    ...found.wishes.map((wish) => ({
      id: `wish:${wish.id}`,
      lon: wish.lon,
      lat: wish.lat,
      kind: "photo" as const,
      image: photoUrl({ id: wish.id, has_photo: wish.has_photo, photo_version: wish.photo_version }, "thumb"),
      icon: kindOf(wish.kind).icon,
      hue: kindOf(wish.kind).hue,
      title: wish.name,
    })),
  ];
}

export function MapScreen({
  onWish,
  onEvent,
  onAdd,
}: {
  onWish: (id: string) => void;
  onEvent: (id: string) => void;
  onAdd: () => void;
}) {
  const area = useArea();
  const [chosen, setScope] = useState<Scope>("near");
  const setup = area ? mapOf(area) : null;
  const scope: Scope = area && !setup ? "world" : chosen;
  const { data: found, found: loading } = useLoad("map", () => readMap());
  const [selected, setSelected] = useState<string | null>(null);

  const points = useMemo(() => (found ? mapPoints(found) : []), [found]);
  const card = selected ? cardOf(found, selected) : null;

  return (
    <main className="outings-map" aria-label={t("tab.map")}>
      {scope === "world" ? (
        <WorldMap
          geoBase={GEO_BASE}
          level="none"
          areas={[]}
          routes={[]}
          places={(found?.wishes ?? []).map((wish) => ({ id: `wish:${wish.id}`, lon: wish.lon, lat: wish.lat, kind: "stay", size: 0.5 }))}
          focus={found && found.wishes.length > 0 ? found.wishes.map((wish) => [wish.lon, wish.lat] as [number, number]) : null}
          onSelectPlace={setSelected}
          label={t("map.world_label")}
        />
      ) : area && setup ? (
        <AreaMap {...setup} view={scope} points={points} selected={selected} onSelect={setSelected} label={t("map.label", { area: area.near })} />
      ) : null}

      <div className="outings-map-top">
        <SegmentedControl label={t("map.scope")} options={scopes(area)} value={scope} onChange={(value) => { setScope(value); setSelected(null); }} />
        <OfflineNotice />
      </div>

      {!found && (
        <div className="outings-map-card">
          <Card>
            <Pending found={loading} rows={1} />
          </Card>
        </div>
      )}

      {card && (
        <div className="outings-map-card">
          <Card flush>
            <List>
              <ListRow
                title={card.title}
                subtitle={card.line}
                image={card.image}
                icon={card.image ? undefined : card.icon}
                hue={card.hue}
                accessory="chevron-right"
                onClick={() => (card.type === "wish" ? onWish(card.id) : onEvent(card.id))}
              />
            </List>
          </Card>
        </div>
      )}

      {found && found.wishes.length === 0 && found.events.length === 0 && !card && (
        <div className="outings-map-card">
          <Card>
            <Hint>{t("map.empty")}</Hint>
            <Button variant="tinted" icon="plus" onClick={onAdd}>
              {t("wishes.add")}
            </Button>
          </Card>
        </div>
      )}
    </main>
  );
}

interface MapCard {
  type: "wish" | "event";
  id: string;
  title: string;
  line: string;
  image?: string;
  icon: IconName;
  hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
}

export function cardOf(found: MapPoints | null, selected: string): MapCard | null {
  const [type, id] = selected.split(":") as ["wish" | "event", string];
  if (type === "wish") {
    const wish = found?.wishes.find((one) => one.id === id);
    if (!wish) return null;
    const kind = kindOf(wish.kind);
    return {
      type,
      id,
      title: wish.name,
      line: [wish.where, kind.label.toLowerCase()].filter(Boolean).join(" · "),
      image: photoUrl({ id: wish.id, has_photo: wish.has_photo, photo_version: wish.photo_version }, "thumb"),
      icon: kind.icon,
      hue: kind.hue,
    };
  }
  const event = found?.events.find((one) => one.id === id);
  if (!event) return null;
  const category = categoryOf(event.category);
  return {
    type,
    id,
    title: event.title,
    line: [shortDay(event.starts_on), event.where, category.label.toLowerCase()].filter(Boolean).join(" · "),
    icon: category.icon,
    hue: category.hue,
  };
}
