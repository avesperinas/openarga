import { invalidate, useResource } from "@openarga/app";
import {
  Button,
  Card,
  Carousel,
  ChoiceChips,
  EmptyState,
  ErrorState,
  List,
  ListRow,
  Notice,
  OfflineNotice,
  PickCard,
  ResourceRow,
  Screen,
  Section,
  SegmentedControl,
  Sheet,
  Skeleton,
  TextAreaField,
  ToggleList,
  ToggleRow,
} from "@openarga/ui";
import { useState } from "react";

import { AppVersion } from "./AppVersion";
import { PICKS, PILLS, type Recommendation, TASTES, changePick, coverOf, readPicks, readPills, readTastes, savePick } from "./api";
import { ScreenHeader, useApp } from "./Header";
import { KINDS, LISTS, ORIGINS, STATES, detailOf, familyOf, nextState, shortDay } from "./taste-words";
import { t } from "./lang";

type ListName = Recommendation["list"];

export function shelf(picks: Recommendation[], list: ListName, hideDone: boolean): Recommendation[] {
  const order = { doing: 0, saved: 1, done: 2, new: 3, dismissed: 4 } as const;
  return picks
    .filter((one) => one.list === list && one.state !== "new" && one.state !== "dismissed")
    .filter((one) => !hideDone || one.state !== "done")
    .sort((a, b) => order[a.state] - order[b.state] || b.updated_at.localeCompare(a.updated_at));
}

export function forYou(picks: Recommendation[]): Recommendation[] {
  return picks
    .filter((one) => one.state === "new")
    .sort((a, b) => Number(b.origin === "weekly") - Number(a.origin === "weekly") || b.created_at.localeCompare(a.created_at))
    .slice(0, 8);
}

const RATINGS = ["1", "2", "3", "4", "5"].map((value) => ({ value, label: `${value} ★` }));

export function LibraryScreen({ onOpenPill }: { onOpenPill: (id: string) => void }) {
  const app = useApp();
  const found = useResource(PICKS, readPicks, { persist: true });
  const pills = useResource(PILLS, readPills, { persist: true }).data ?? [];
  const families = useResource(TASTES, readTastes, { persist: true }).data?.families ?? [];
  const [list, setList] = useState<ListName>("read");
  const [hideDone, setHideDone] = useState(false);
  const [rating, setRating] = useState<Recommendation | null>(null);
  const [problem, setProblem] = useState("");
  const picks = found.data ?? null;

  const change = (pick: Recommendation, update: Parameters<typeof changePick>[1]) =>
    changePick(pick.id, update)
      .then(() => invalidate(PICKS))
      .catch(() => setProblem(t("error.change")));

  const save = (pick: Recommendation) =>
    savePick(pick.id)
      .then(() => invalidate(PICKS))
      .catch((error: unknown) => {
        invalidate(PICKS);
        setProblem(error instanceof Error ? error.message : t("error.save"));
      });

  const advance = (pick: Recommendation) => {
    const next = nextState(pick.state);
    void change(pick, { state: next });
    if (next === "done") setRating({ ...pick, state: next });
  };

  const counts = Object.fromEntries(
    LISTS.map((one) => [one.value, picks ? shelf(picks, one.value, true).length : 0]),
  ) as Record<ListName, number>;

  return (
    <Screen>
      <ScreenHeader title={t("library.title")} />
      <OfflineNotice />
      {problem && <Notice tone="warning">{problem}</Notice>}
      {found.loading && !picks && <Skeleton label={t("library.opening")} />}
      {!picks && found.error && <ErrorState title={t("library.failed")} detail={found.error.message} onRetry={found.refresh} />}

      {picks && forYou(picks).length > 0 && (
        <Section title={t("library.for_you")} count={forYou(picks).length}>
          <Carousel label={t("library.for_you")}>
            {forYou(picks).map((pick) => (
              <PickCard
                key={pick.id}
                cover={coverOf(pick)}
                icon={KINDS[pick.kind].icon}
                hue={KINDS[pick.kind].hue}
                kind={KINDS[pick.kind].label}
                title={pick.title}
                detail={detailOf(pick)}
                why={pick.why}
                actions={
                  <>
                    <Button variant="primary" icon="plus" onClick={() => void save(pick)}>
                      {t("action.save")}
                    </Button>
                    <Button variant="plain" onClick={() => void change(pick, { state: "dismissed" })}>
                      {t("library.not_for_me")}
                    </Button>
                  </>
                }
              />
            ))}
          </Carousel>
        </Section>
      )}

      {picks && (
        <>
          <SegmentedControl
            label={t("library.which_list")}
            value={list}
            onChange={setList}
            options={LISTS.map((one) => ({
              value: one.value,
              label: counts[one.value] ? `${one.label} · ${counts[one.value]}` : one.label,
              icon: one.icon,
            }))}
          />
          <ToggleList>
            <ToggleRow name={t("library.hide_done")} checked={hideDone} onChange={setHideDone} />
          </ToggleList>
          {shelf(picks, list, hideDone).length === 0 ? (
            <EmptyState icon={LISTS.find((one) => one.value === list)!.icon} hue={5} title={t("library.empty")}>
              {t("library.empty_detail")}
            </EmptyState>
          ) : (
            <Card>
              {shelf(picks, list, hideDone).map((pick) => (
                <ResourceRow
                    key={pick.id}
                    cover={coverOf(pick)}
                    icon={KINDS[pick.kind].icon}
                    hue={KINDS[pick.kind].hue}
                    title={pick.title}
                    href={pick.links[0]?.url}
                    detail={[
                      KINDS[pick.kind].label,
                      detailOf(pick),
                      pick.sent_to ? t("library.in_reading") : null,
                      pick.rating !== null ? `${pick.rating} ★` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    why={pick.why}
                    saved={false}
                    action={
                      <Button variant={pick.state === "done" ? "plain" : "secondary"} onClick={() => advance(pick)}>
                        {STATES[pick.state]}
                      </Button>
                    }
                  />
              ))}
            </Card>
          )}
        </>
      )}

      {pills.length > 0 && (
        <Section title={t("library.pills")} count={pills.length}>
          <List>
            {pills.map((pill) => {
              const family = familyOf(families, pill.family_key);
              return (
                <ListRow
                  key={pill.id}
                  icon="spark"
                  hue={family.hue}
                  title={pill.headline}
                  subtitle={`${family.name} · ${shortDay(pill.day)} · ${ORIGINS[pill.origin]}`}
                  accessory="chevron-right"
                  onClick={() => onOpenPill(pill.id)}
                />
              );
            })}
          </List>
        </Section>
      )}

      {rating && <RateSheet pick={rating} name={app.name} onClose={() => setRating(null)} onSave={(update) => change(rating, update)} />}
      <AppVersion />
    </Screen>
  );
}

function RateSheet({
  pick,
  name,
  onClose,
  onSave,
}: {
  pick: Recommendation;
  name: string;
  onClose: () => void;
  onSave: (update: Parameters<typeof changePick>[1]) => Promise<unknown>;
}) {
  const [stars, setStars] = useState<string | null>(pick.rating ? String(Math.round(pick.rating)) : null);
  const [more, setMore] = useState<boolean>(pick.more_like ?? false);
  const [note, setNote] = useState(pick.note ?? "");
  return (
    <Sheet
      title={t("library.rate_title", { title: pick.title })}
      onClose={onClose}
      foot={t("library.rate_foot", { name })}
      action={{
        label: t("action.save"),
        onClick: () => {
          void onSave({ rating: stars ? Number(stars) : null, more_like: more, note: note.trim() || null }).then(onClose);
        },
      }}
    >
      <ChoiceChips label={t("library.your_rating")} options={RATINGS} value={stars} onChange={setStars} />
      <ToggleList>
        <ToggleRow name={t("library.more_like")} detail={t("library.more_like_detail")} checked={more} onChange={setMore} />
      </ToggleList>
      <TextAreaField label={t("library.note")} value={note} onChange={setNote} rows={3} max={600} />
    </Sheet>
  );
}
