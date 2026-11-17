import {
  Button,
  ConfirmDelete,
  cannotUndo,
  GroupLabel,
  Hint,
  Icon,
  Screen,
  Sheet,
  TextField,
} from "@openarga/ui";
import { WorldMap } from "@openarga/ui/world-map";
import { type CSSProperties, useEffect, useMemo, useState } from "react";

import {
  type Category,
  type Leg,
  type Place,
  type Space,
  type Stay,
  type Trip,
  type Visit,
  Unauthorised,
  archiveTrip,
  deleteTrip,
  readBookings,
  readSpaces,
  readTrip,
  removeCover,
  setSummary,
  uploadCover,
  setStatus,
  shareTrip,
  signIn,
} from "./api";
import type { Navigate, Route } from "./App";
import { areasOf, placesOf, pointsOf, routesOf } from "./atlas";
import { BalanceSection } from "./Balance";
import { ChecklistSection } from "./Checklist";
import { DocumentsSection } from "./Documents";
import { ScreenHeader } from "./Header";
import { useMembers } from "./people";
import { TravellersSection } from "./Travellers";
import { JournalSection } from "./Journal";
import { later } from "./Later";
import { Pending, useLoad } from "./Loads";
import { CannotKeep, prepare } from "./prepare";
import { SharePicker } from "./SharePicker";
import { TripHero, TripTabs } from "./TripChrome";
import { lock, standalone, tripAppPath } from "./tripApp";
import { CATEGORIES, MODES, dateRange, dayLabel, euros, eurosExact, flag, km, nights, where } from "./words";
import { plural, t } from "./lang";

type Step =
  | { kind: "leg"; day: string | null; leg: Leg }
  | { kind: "stay"; day: string; stay: Stay; visits: Visit[] }
  | { kind: "visit"; day: string | null; visit: Visit };

const NotesSection = later(() => import("./Notes").then((found) => found.NotesSection), { screen: false });

export function itinerary(trip: Trip): Step[] {
  const steps: { step: Step; key: string }[] = [];
  const under = new Set<string>();
  for (const stay of trip.stays) {
    const visits = trip.visits.filter((one) => one.stay_id === stay.id);
    visits.forEach((one) => under.add(one.id));
    steps.push({ step: { kind: "stay", day: stay.arrives_on, stay, visits }, key: `${stay.arrives_on}1` });
  }
  for (const leg of trip.legs) {
    const arriving = trip.stays.find((one) => one.place.id === leg.to_place.id);
    const day = leg.travelled_on ?? arriving?.arrives_on ?? trip.ends_on;
    steps.push({ step: { kind: "leg", day: leg.travelled_on, leg }, key: `${day}0` });
  }
  for (const visit of trip.visits) {
    if (under.has(visit.id)) continue;
    steps.push({ step: { kind: "visit", day: visit.visited_on, visit }, key: `${visit.visited_on ?? trip.ends_on}2` });
  }
  return steps.sort((a, b) => a.key.localeCompare(b.key)).map((one) => one.step);
}

export function TripScreen({
  id,
  tab = "trip",
  home,
  navigate,
  onChanged,
}: {
  id: string;
  tab?: "trip" | "money" | "notes" | "journal" | "settings";
  home: Place | null;
  navigate: Navigate;
  onChanged: () => void;
}) {
  const loaded = useLoad<Trip>(`trip/${id}`, () => readTrip(id));
  const trip = loaded.data;
  const setTrip = loaded.set;
  const [peopleVersion, setPeopleVersion] = useState(0);
  const members = useMembers(trip?.space_id ?? null);
  const [problem, setProblem] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [preparing, setPreparing] = useState<string | null>(null);
  const [prepared, setPrepared] = useState("");
  const [installHint, setInstallHint] = useState(false);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [covering, setCovering] = useState(false);
  const [summarising, setSummarising] = useState<string | null>(null);
  const [pending, setPending] = useState<number | null>(null);

  useEffect(() => {
    readBookings(id)
      .then((found) => setPending(found.filter((one) => !one.booked).length))
      .catch(() => setPending(null));
  }, [id]);

  useEffect(() => {
    readSpaces()
      .then(setSpaces)
      .catch(() => setSpaces([]));
  }, []);

  const map = useMemo(
    () =>
      trip
        ? {
            areas: areasOf([trip], "country", [], home),
            places: placesOf([trip]),
            routes: routesOf([trip]),
            focus: pointsOf(trip),
          }
        : null,
    [trip, home],
  );
  const list: Route = trip && trip.phase !== "done" ? { screen: "plans" } : { screen: "trips" };
  const back =
    lock() === id
      ? undefined
      : { label: list.screen === "plans" ? t("nav.plans") : t("nav.trips"), onClick: () => navigate(list) };

  if (!trip || !map) {
    return (
      <Screen>
        <ScreenHeader title={t("trip.title")} back={back} />
        <Pending found={loaded.found} label={t("trip.loading")} />
      </Screen>
    );
  }

  const steps = itinerary(trip);
  const byCategory = (Object.keys(CATEGORIES) as Category[]).map((category) => ({
    category,
    items: trip.expenses.filter((one) => one.category === category),
    total: trip.spend.by_category[category] ?? 0,
  }));

  return (
    <Screen>
      <ScreenHeader
        eyebrow={trip.archived ? t("trip.archived") : undefined}
        title={trip.title}
        back={back}
      />
      <TripHero trip={trip} onCover={() => setCovering(true)} />
      <TripTabs id={trip.id} active={tab === "settings" ? "tripsettings" : tab} navigate={navigate} />

      {tab === "trip" && (
        <>
      <button
        type="button"
        className="travel-summary"
        data-empty={trip.summary ? undefined : true}
        onClick={() => setSummarising(trip.summary ?? "")}
      >
        {trip.summary ?? t("trip.summary_empty")}
      </button>
      <dl className="travel-kpis">
        <div className="surface">
          <dt>{t("trip.kpi.days")}</dt>
          <dd>{trip.days}</dd>
        </div>
        <div className="surface">
          <dt>{trip.phase === "done" ? t("trip.kpi.spent") : t("trip.kpi.so_far")}</dt>
          <dd>{euros(trip.spend.group)}</dd>
        </div>
        <div className="surface">
          <dt>{t("trip.kpi.travellers")}</dt>
          <dd>{trip.travellers}</dd>
        </div>
        <div className="surface">
          <dt>{t("trip.kpi.to_book")}</dt>
          <dd>{pending ?? "—"}</dd>
        </div>
      </dl>

      <div className="surface travel-trip-map">
        <WorldMap
          geoBase="/travel/geo/"
          level="country"
          areas={map.areas}
          places={map.places}
          routes={map.routes}
          highlight={trip.id}
          focus={map.focus.length ? map.focus : null}
          label={t("trip.map_of", { title: trip.title })}
        />
      </div>

      <Hint>
        {trip.countries.map((code) => flag(code)).join(" ")}
        {` · ${plural(trip.travellers, "count.travellers")}`}
        {trip.companions.length > 0 && ` · ${t("trip.with", { names: trip.companions.join(", ") })}`}
        {trip.km > 0 && ` · ${km(trip.km)}`}
      </Hint>
      {trip.tags.length > 0 && (
        <div className="chips" aria-label={t("trip.tags")}>
          {trip.tags.map((tag) => (
            <span key={tag} className="chip" aria-pressed="true">
              {tag}
            </span>
          ))}
        </div>
      )}

      <section className="travel-group">
        <GroupLabel>{t("trip.shared")}</GroupLabel>
        <SharePicker
          trip={trip}
          spaces={spaces}
          onChoose={async (spaceId) => {
            try {
              setTrip(await shareTrip(trip.id, spaceId));
              onChanged();
            } catch (error) {
              if (error instanceof Unauthorised) return signIn();
              setProblem(error instanceof Error ? error.message : t("trip.error.share"));
            }
          }}
        />
      </section>

      <section className="travel-group">
        <GroupLabel>{t("trip.itinerary")}</GroupLabel>
        {steps.length === 0 ? (
          <Hint>{t("trip.no_places")}</Hint>
        ) : (
          <ol className="surface travel-timeline">
            {steps.map((step) => (
              <TimelineStep key={step.kind + (step.kind === "leg" ? step.leg.id : step.kind === "stay" ? step.stay.id : step.visit.id)} step={step} />
            ))}
          </ol>
        )}
      </section>

        </>
      )}

      {tab === "money" && (
        <>
      <section className="travel-group">
        <GroupLabel>{t("trip.spending")}</GroupLabel>
        {trip.budget_eur != null && <BudgetBar budget={trip.budget_eur} spent={trip.spend.per_person} />}
        {trip.expenses.length === 0 ? (
          <Hint>{t("trip.no_spending")}</Hint>
        ) : (
          <div className="surface travel-spend">
            <dl className="travel-spend-totals">
              <div>
                <dt>{t("trip.per_person")}</dt>
                <dd>{euros(trip.spend.per_person)}</dd>
              </div>
              <div>
                <dt>{t("trip.group")}</dt>
                <dd>{euros(trip.spend.group)}</dd>
              </div>
              <div>
                <dt>{t("trip.per_day")}</dt>
                <dd>{trip.spend.per_day !== null ? euros(trip.spend.per_day) : "—"}</dd>
              </div>
            </dl>
            {byCategory
              .filter((one) => one.items.length)
              .map((one) => (
                <div key={one.category} className="travel-spend-category">
                  <GroupLabel>
                    {CATEGORIES[one.category]}
                    <span className="travel-group-detail">{eurosExact(one.total)}</span>
                  </GroupLabel>
                  <ul className="travel-spend-items">
                    {one.items.map((item) => (
                      <li key={item.id}>
                        <span>
                          {item.concept}
                          {trip.space_id !== null && !item.mine && (
                            <span className="travel-step-detail"> · {t("trip.noted_by_other")}</span>
                          )}
                        </span>
                        <span>{eurosExact(item.amount_eur)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            <p className="travel-footnote">
              {t("trip.footnote", {
                people: plural(trip.travellers, "count.people"),
                days: plural(trip.days, "count.days"),
              })}
            </p>
          </div>
        )}
      </section>

      <TravellersSection trip={trip} members={members} onChanged={() => setPeopleVersion((now) => now + 1)} />
      <BalanceSection tripId={trip.id} version={`${trip.expenses.length}-${peopleVersion}`} members={members} />
        </>
      )}

      {tab === "journal" && <JournalSection trip={trip} />}
      {tab === "notes" && (
        <>
          {trip.notes && <Hint lines>{trip.notes}</Hint>}
          <NotesSection tripId={trip.id} />
          <ChecklistSection trip={trip} members={members} version={peopleVersion} />
          <DocumentsSection tripId={trip.id} />
        </>
      )}

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {tab === "trip" && trip.phase === "plan" && (
        <Hint>{t("trip.plan_hint")}</Hint>
      )}
      {tab === "settings" && (
        <>
      {prepared && <Hint>{prepared}</Hint>}
      {installHint && (
        <Hint>
          {t("trip.install_hint")}
        </Hint>
      )}
      <div className="travel-actions">
        {trip.phase !== "done" && (
          <Button
            variant="secondary"
            icon="pull"
            disabled={preparing !== null}
            onClick={async () => {
              setPreparing(t("trip.offline.preparing"));
              try {
                const failed = await prepare(trip.id, (done, total) =>
                  setPreparing(t("trip.offline.saving", { done, total })),
                );
                setPrepared(
                  failed
                    ? t("trip.offline.partial", { failed })
                    : t("trip.offline.done"),
                );
              } catch (error) {
                if (error instanceof Unauthorised) return signIn();
                setPrepared(
                  error instanceof CannotKeep ? error.message : t("trip.offline.failed"),
                );
              } finally {
                setPreparing(null);
              }
            }}
          >
            {preparing ?? t("trip.offline.prepare")}
          </Button>
        )}
        {trip.phase !== "done" && lock() !== trip.id && (
          <Button
            variant="secondary"
            icon="phone"
            onClick={() =>
              standalone() ? setInstallHint(true) : window.location.assign(tripAppPath(trip.id))
            }
          >
            {t("trip.iphone_app")}
          </Button>
        )}
        <Button variant="secondary" icon="edit" onClick={() => navigate({ screen: "edit", id: trip.id })}>
          {t("trip.edit")}
        </Button>
        {(trip.phase === "plan" || trip.phase === "upcoming") && (
          <Button
            variant={trip.phase === "plan" ? "tinted" : "secondary"}
            icon={trip.phase === "plan" ? "calendar" : "undo"}
            disabled={confirming}
            onClick={async () => {
              setConfirming(true);
              try {
                setTrip(await setStatus(trip.id, trip.phase === "plan" ? "confirmed" : "plan"));
                onChanged();
              } catch (error) {
                if (error instanceof Unauthorised) return signIn();
                setProblem(error instanceof Error ? error.message : t("trip.error.change"));
              } finally {
                setConfirming(false);
              }
            }}
          >
            {trip.phase === "plan" ? t("trip.confirm") : t("trip.back_to_plan")}
          </Button>
        )}
        <Button
          variant="secondary"
          icon={trip.archived ? "undo" : undefined}
          disabled={archiving}
          onClick={async () => {
            setArchiving(true);
            try {
              setTrip(await archiveTrip(trip.id, !trip.archived));
              onChanged();
            } catch (error) {
              if (error instanceof Unauthorised) return signIn();
              setProblem(error instanceof Error ? error.message : t("trip.error.archive"));
            } finally {
              setArchiving(false);
            }
          }}
        >
          {trip.archived ? t("action.unarchive") : t("action.archive")}
        </Button>
        {trip.mine && (
          <Button variant="destructive" icon="trash" onClick={() => setDeleting(true)}>
            {t("trip.delete")}
          </Button>
        )}
      </div>

        </>
      )}

      {covering && (
        <CoverSheet
          trip={trip}
          onClose={() => setCovering(false)}
          onSaved={(saved) => {
            setTrip(saved);
            setCovering(false);
            onChanged();
          }}
        />
      )}
      {summarising !== null && (
        <Sheet
          title={t("trip.summary_title")}
          onClose={() => setSummarising(null)}
          action={{
            label: t("action.save"),
            onClick: async () => {
              try {
                setTrip(await setSummary(trip, summarising));
                setSummarising(null);
              } catch (error) {
                if (error instanceof Unauthorised) return signIn();
                setProblem(error instanceof Error ? error.message : t("trip.error.summary"));
                setSummarising(null);
              }
            },
          }}
        >
          <TextField
            label={t("trip.summary")}
            value={summarising}
            onChange={(value) => setSummarising(value.slice(0, 1000))}
            placeholder={t("trip.summary_example")}
            autoFocus
          />
        </Sheet>
      )}

      {deleting && (
        <ConfirmDelete
          title={t("trip.delete_confirm")}
          subject={`${trip.title} · ${dateRange(trip.starts_on, trip.ends_on)}`}
          consequence={`${t("trip.delete_consequence")} ${cannotUndo()}`}
          action={t("trip.delete")}
          onCancel={() => setDeleting(false)}
          onConfirm={async () => {
            await deleteTrip(trip.id);
            onChanged();
            navigate(list);
          }}
        />
      )}
    </Screen>
  );
}

function TimelineStep({ step }: { step: Step }) {
  if (step.kind === "leg") {
    const { leg } = step;
    return (
      <li className="travel-step" data-kind="leg">
        <span className="travel-step-mark">
          <Icon name={MODES[leg.mode].icon} />
        </span>
        <span className="travel-step-text">
          <span className="travel-step-title">
            {leg.from_place.name} → {leg.to_place.name}
          </span>
          <span className="travel-step-detail">
            {MODES[leg.mode].label}
            {leg.km !== null && ` · ${km(leg.km)}`}
            {leg.travelled_on && ` · ${dayLabel(leg.travelled_on)}`}
          </span>
        </span>
      </li>
    );
  }
  if (step.kind === "stay") {
    const { stay, visits } = step;
    return (
      <li className="travel-step" data-kind="stay">
        <span className="travel-step-mark">
          <Icon name="pin" />
        </span>
        <span className="travel-step-text">
          <span className="travel-step-title">
            {flag(stay.place.country_code)} {stay.place.name}
          </span>
          <span className="travel-step-detail">
            {dateRange(stay.arrives_on, stay.leaves_on)} · {nights(stay.nights)}
            {stay.accommodation && ` · ${stay.accommodation}`}
          </span>
          {stay.place.lat === null && <span className="travel-step-warning">{t("trip.not_on_map")}</span>}
          {visits.length > 0 && (
            <ul className="travel-step-visits">
              {visits.map((visit) => (
                <li key={visit.id}>
                  {where(visit.place).split(",")[0]}
                  {visit.visited_on && <span className="travel-step-detail"> · {dayLabel(visit.visited_on)}</span>}
                  {visit.note && <span className="travel-step-detail"> · {visit.note}</span>}
                </li>
              ))}
            </ul>
          )}
        </span>
      </li>
    );
  }
  const { visit } = step;
  return (
    <li className="travel-step" data-kind="visit">
      <span className="travel-step-mark travel-step-mark-soft">
        <Icon name="pin" />
      </span>
      <span className="travel-step-text">
        <span className="travel-step-title">{visit.place.name}</span>
        <span className="travel-step-detail">
          {t("trip.visiting")}{visit.visited_on && ` · ${dayLabel(visit.visited_on)}`}
          {visit.note && ` · ${visit.note}`}
        </span>
      </span>
    </li>
  );
}

export function BudgetBar({ budget, spent }: { budget: number; spent: number }) {
  const share = budget > 0 ? Math.min(1, spent / budget) : 1;
  const over = spent > budget;
  return (
    <div className="surface travel-budget" data-over={over || undefined}>
      <div className="travel-budget-line">
        <span>
          {t("budget.of", { spent: euros(spent), budget: euros(budget) })}
        </span>
        <strong>{over ? t("budget.over", { amount: euros(spent - budget) }) : t("budget.left", { amount: euros(budget - spent) })}</strong>
      </div>
      <div
        className="travel-budget-track"
        role="meter"
        aria-label={t("budget.spent")}
        aria-valuemin={0}
        aria-valuemax={budget}
        aria-valuenow={spent}
      >
        <span className="travel-budget-fill" style={{ "--used": `${share * 100}%` } as CSSProperties} />
      </div>
    </div>
  );
}

function CoverSheet({ trip, onClose, onSaved }: { trip: Trip; onClose: () => void; onSaved: (trip: Trip) => void }) {
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<Trip>) => {
    setBusy(true);
    try {
      onSaved(await action());
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("cover.error"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet title={t("cover.title")} onClose={onClose}>
      <div className="travel-sheet-stack">
        <label className="travel-cover-pick">
          <Icon name="camera" />
          {busy ? t("cover.uploading") : t("cover.choose")}
          <input
            type="file"
            accept="image/*"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void run(() => uploadCover(trip.id, file));
            }}
          />
        </label>
        {trip.cover?.page && (
          <Hint>{t("cover.hint")}</Hint>
        )}
        {trip.cover && (
          <Button variant="destructive" icon="trash" disabled={busy} onClick={() => void run(() => removeCover(trip.id))}>
            {t("cover.remove")}
          </Button>
        )}
        {problem && <Hint tone="warning">{problem}</Hint>}
      </div>
    </Sheet>
  );
}
