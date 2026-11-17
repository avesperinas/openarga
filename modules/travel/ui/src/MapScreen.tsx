import {
  Button,
  CheckChips,
  ErrorState,
  GroupLabel,
  Heading,
  Hint,
  IconButton,
  List,
  ListRow,
  SegmentedControl,
  SelectField,
  Sheet,
} from "@openarga/ui";
import { MapFigures, type MapLevel, TimeBar, WorldMap } from "@openarga/ui/world-map";
import { useEffect, useMemo, useState } from "react";

import type { Mode, OtherPlace, Place, Trip } from "./api";
import type { Navigate } from "./App";
import { HomeLink } from "./Header";
import {
  type Filters,
  activeFilters,
  areasOf,
  insideArea,
  matches,
  noFilters,
  options,
  othersShown,
  pointsOf,
  talliesOf,
  yearSpan,
  GEO,
} from "./atlas";
import { MODES, dateRange, flag, km, nights, trips as tripsWord, whole } from "./words";
import { t } from "./lang";

export type AreaLevel = Exclude<MapLevel, "none">;

type Panel = { kind: "area"; code: string; name: string } | { kind: "place"; id: string };

export function MapScreen({
  trips,
  others,
  home,
  problem,
  onRetry,
  navigate,
}: {
  trips: Trip[] | null;
  others: OtherPlace[];
  home: Place | null;
  problem: string;
  onRetry: () => Promise<void>;
  navigate: Navigate;
}) {
  const all = useMemo(() => trips ?? [], [trips]);
  const [level, setLevel] = useState<AreaLevel>("country");
  const [filters, setFilters] = useState<Filters>(() => noFilters(all));
  const [editing, setEditing] = useState(false);
  const [panel, setPanel] = useState<Panel | null>(null);

  useEffect(() => {
    if (trips) setFilters((now) => ({ ...now, years: yearSpan(trips) }));
  }, [trips]);

  const shown = useMemo(() => all.filter((one) => matches(one, filters)), [all, filters]);
  const extra = useMemo(() => othersShown(others, filters, all), [others, filters, all]);
  const areas = useMemo(
    () => areasOf(shown, level, extra, home),
    [shown, level, extra, home],
  );
  const tallies = talliesOf(shown, extra);
  const focusTrip = filters.trip ? all.find((one) => one.id === filters.trip) : undefined;
  const focus = focusTrip ? pointsOf(focusTrip) : null;
  const [min, max] = yearSpan(all);
  const chosen = activeFilters(filters);

  return (
    <main className="travel-map-screen">
      <WorldMap
        geoBase={GEO}
        level={level}
        areas={areas}
        places={[]}
        routes={[]}
        focus={focus}
        selected={panel?.kind === "area" ? panel.code : null}
        label={t("atlas.map")}
        onSelectArea={(code, name) => setPanel({ kind: "area", code, name })}
      />

      <div className="travel-map-top">
        <MapFigures
          figures={[
            level === "country"
              ? { label: t("stats.countries"), value: whole(tallies.countries) }
              : { label: t("atlas.regions"), value: whole(tallies.regions) },
            { label: t("nav.trips"), value: whole(tallies.trips) },
            { label: t("stats.nights"), value: whole(tallies.nights) },
          ]}
        />
        <HomeLink />
        <div className="travel-map-level glass">
          <SegmentedControl
            label={t("atlas.level")}
            value={level}
            onChange={setLevel}
            options={[
              { value: "country", label: t("stats.countries") },
              { value: "region", label: t("atlas.regions") },
            ]}
          />
        </div>
        <div className="travel-map-filter glass">
          <IconButton
            icon="filter"
            label={chosen ? t("atlas.filters_on", { count: chosen }) : t("atlas.filters")}
            variant="plain"
            onClick={() => setEditing(true)}
          />
          {chosen > 0 && <span className="travel-badge">{chosen}</span>}
        </div>
        {problem && (
          <div className="travel-map-problem">
            <ErrorState title={t("error.no_answer")} detail={problem} onRetry={onRetry} />
          </div>
        )}
        {trips && trips.length === 0 && others.length === 0 && (
          <div className="travel-map-empty glass">
            <Heading>{t("atlas.empty")}</Heading>
            <Hint>
              {t("atlas.empty_detail")}
            </Hint>
            <Button variant="primary" icon="plus" onClick={() => navigate({ screen: "edit", id: null })}>
              {t("atlas.add_trip")}
            </Button>
          </div>
        )}
      </div>

      <div className="travel-map-bottom">
        {focusTrip && (
          <button
            type="button"
            className="travel-map-chosen glass"
            onClick={() => navigate({ screen: "trip", id: focusTrip.id })}
          >
            <span className="travel-map-chosen-title">{focusTrip.title}</span>
            <span className="travel-map-chosen-detail">
              {dateRange(focusTrip.starts_on, focusTrip.ends_on)} · {nights(focusTrip.nights)}
            </span>
          </button>
        )}
        {all.length > 0 && (
          <TimeBar
            min={min}
            max={max}
            value={filters.years}
            onChange={(years) => setFilters((now) => ({ ...now, years }))}
          />
        )}
      </div>

      {editing && (
        <FiltersSheet
          trips={all}
          filters={filters}
          onChange={setFilters}
          onClose={() => setEditing(false)}
        />
      )}
      {panel && (
        <PanelSheet
          panel={panel}
          trips={shown}
          others={extra}
          level={level}
          navigate={navigate}
          onClose={() => setPanel(null)}
        />
      )}
    </main>
  );
}

function FiltersSheet({
  trips,
  filters,
  onChange,
  onClose,
}: {
  trips: Trip[];
  filters: Filters;
  onChange: (filters: Filters) => void;
  onClose: () => void;
}) {
  const choices = options(trips);
  const NONE = "";
  return (
    <Sheet
      title={t("atlas.filters")}
      onClose={onClose}
      action={{ label: t("atlas.clear_filters"), onClick: () => onChange({ ...noFilters(trips) }), disabled: !activeFilters(filters) }}
    >
      <div className="travel-sheet-stack">
        <SelectField
          label={t("trip.title")}
          value={filters.trip ?? NONE}
          onChange={(value) => onChange({ ...filters, trip: value || null })}
          options={[
            { value: NONE, label: t("map.all") },
            ...trips.map((one) => ({ value: one.id, label: `${one.title} · ${one.starts_on.slice(0, 4)}` })),
          ]}
        />
        {choices.companions.length > 0 && (
          <section className="travel-sheet-group">
            <GroupLabel>{t("editor.companions")}</GroupLabel>
            <CheckChips
              label={t("editor.companions")}
              values={filters.companions}
              onChange={(companions) => onChange({ ...filters, companions })}
              options={choices.companions.map((one) => ({ value: one, label: one }))}
            />
          </section>
        )}
        {choices.tags.length > 0 && (
          <section className="travel-sheet-group">
            <GroupLabel>{t("atlas.tag")}</GroupLabel>
            <CheckChips
              label={t("atlas.tag")}
              values={filters.tags}
              onChange={(tags) => onChange({ ...filters, tags })}
              options={choices.tags.map((one) => ({ value: one, label: one }))}
            />
          </section>
        )}
        {choices.modes.length > 0 && (
          <section className="travel-sheet-group">
            <GroupLabel>{t("editor.mode")}</GroupLabel>
            <CheckChips<Mode>
              label={t("editor.mode")}
              values={filters.modes}
              onChange={(modes) => onChange({ ...filters, modes })}
              options={choices.modes.map((one) => ({ value: one, label: MODES[one].label }))}
            />
          </section>
        )}
      </div>
    </Sheet>
  );
}

function PanelSheet({
  panel,
  trips,
  others,
  level,
  navigate,
  onClose,
}: {
  panel: Panel;
  trips: Trip[];
  others: OtherPlace[];
  level: MapLevel;
  navigate: Navigate;
  onClose: () => void;
}) {
  if (panel.kind === "place") {
    const found = trips.filter(
      (one) => one.stays.some((s) => s.place.id === panel.id) || one.visits.some((v) => v.place.id === panel.id),
    );
    const place =
      found.flatMap((one) => [...one.stays, ...one.visits]).find((one) => one.place.id === panel.id)?.place ?? null;
    const slept = found.flatMap((one) => one.stays).filter((one) => one.place.id === panel.id);
    return (
      <Sheet title={place ? `${flag(place.country_code)} ${place.name}` : t("atlas.place")} onClose={onClose}>
        <Hint>
          {[place?.region, place?.country].filter(Boolean).join(", ")}
          {slept.length ? ` · ${nights(slept.reduce((sum, one) => sum + one.nights, 0))}` : ` · ${t("atlas.visited")}`}
        </Hint>
        <TripList trips={found} navigate={navigate} />
      </Sheet>
    );
  }
  const inside = insideArea(trips, panel.code, level === "region" ? "region" : "country", others);
  const countryFlag = level === "region" ? flag(panel.code.slice(0, 2)) : flag(panel.code);
  return (
    <Sheet title={`${countryFlag} ${panel.name}`} onClose={onClose}>
      {inside.trips.length === 0 && inside.others.length === 0 && (
        <Hint>{t("atlas.never_here")}</Hint>
      )}
      {inside.trips.length > 0 && (
        <>
          <Hint>
            {tripsWord(inside.trips.length)} · {inside.nights ? nights(inside.nights) : t("atlas.no_nights")}
          </Hint>
          <p className="travel-places">{inside.places.join(" · ")}</p>
          <TripList trips={inside.trips.map((one) => one.trip)} navigate={navigate} />
        </>
      )}
      {inside.others.length > 0 && (
        <Hint>{t("atlas.no_trip", { names: inside.others.map((one) => one.place.name).join(" · ") })}</Hint>
      )}
    </Sheet>
  );
}

function TripList({ trips, navigate }: { trips: Trip[]; navigate: Navigate }) {
  return (
    <List>
      {trips.map((one) => (
        <ListRow
          key={one.id}
          title={one.title}
          detail={`${dateRange(one.starts_on, one.ends_on)} · ${nights(one.nights)}`}
          value={one.km ? km(one.km) : undefined}
          accessory="chevron-right"
          onClick={() => navigate({ screen: "trip", id: one.id })}
        />
      ))}
    </List>
  );
}
