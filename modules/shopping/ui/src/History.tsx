import {
  ChoiceChips,
  EmptyState,
  ErrorState,
  FrequencyRow,
  FrequencyRows,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  Section,
  Sheet,
  Skeleton,
  todayIso,
  type Translate,
  useT,
} from "@openarga/ui";
import { mutate, useResource } from "@openarga/app";
import { useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Category,
  type Product,
  type ShoppingList,
  type Trip,
  Unauthorised,
  readCategories,
  readProducts,
  readTrips,
  setCategory,
  signIn,
} from "./api";
import { ScreenHeader } from "./Header";
import { dayLabel, daysSince, habitDetail, sectionName } from "./words";

export function HistoryScreen({ onList }: { onList: () => void }) {
  const t = useT();
  const done = useResource("trips", readTrips);
  const trips = done.data ?? null;
  const products = useResource("products", () => readProducts(), { persist: true }).data ?? [];
  const categories = useResource("categories", readCategories, { staleMs: 86_400_000, persist: true }).data ?? [];
  const [trip, setTrip] = useState<Trip | null>(null);
  const [product, setProduct] = useState<Product | null>(null);

  const bought = products.filter((one) => one.times > 0);
  const today = todayIso();
  const byOverdue = [...bought].sort((a, b) => overdue(b, today) - overdue(a, today));

  return (
    <Screen>
      <ScreenHeader title={t("history.title")} />
      <OfflineNotice />

      {done.error && trips === null && (
        <ErrorState title={t("history.read_failed")} detail={done.error.message} onRetry={done.refresh} />
      )}
      {done.loading && <Skeleton label={t("history.loading")} />}

      {trips !== null && trips.length === 0 && (
        <EmptyState
          icon="calendar"
          title={t("history.empty")}
          action={{ label: t("history.go_list"), icon: "basket", onClick: onList }}
        >
          {t("history.empty_body")}
        </EmptyState>
      )}

      {trips && trips.length > 0 && (
        <Section title={t("history.trips")} count={trips.length}>
          <List>
            {trips.map((one) => (
              <ListRow
                key={one.id}
                title={dayLabel(one.finished_at)}
                detail={one.items === 1 ? t("history.products_one") : t("history.products_other", { count: one.items })}
                accessory="chevron-right"
                onClick={() => setTrip(one)}
              />
            ))}
          </List>
        </Section>
      )}

      {bought.length > 0 && (
        <Section title={t("history.bought")}>
          <FrequencyRows label={t("history.bought")}>
            {byOverdue.map((one) => {
              const since = daysSince(one.last, today);
              return (
                <FrequencyRow
                  key={one.id}
                  title={one.name}
                  since={since}
                  every={one.every_days}
                  label={`${one.name}: ${habitDetail(t, one)}`}
                  value={since === null ? undefined : one.every_days ? `${since} / ${Math.round(one.every_days)} d` : `${since} d`}
                  onClick={() => setProduct(one)}
                />
              );
            })}
          </FrequencyRows>
        </Section>
      )}

      {trip && (
        <Sheet title={dayLabel(trip.finished_at)} onClose={() => setTrip(null)}>
          <List>
            {trip.products.map((one) => (
              <ListRow key={one.name} title={one.name} detail={one.quantity ?? undefined} />
            ))}
          </List>
        </Sheet>
      )}
      {product && (
        <ProductSheet
          product={product}
          categories={categories}
          onClose={() => setProduct(null)}
          onSaved={(categoryId, fresh) => {
            void mutate("list", fresh);
            void mutate<Product[]>("products", (now) =>
              (now ?? []).map((one) => (one.id === product.id ? { ...one, category_id: categoryId } : one)),
            );
            setProduct(null);
          }}
        />
      )}
      <AppVersion />
    </Screen>
  );
}

function ProductSheet({
  product,
  categories,
  onClose,
  onSaved,
}: {
  product: Product;
  categories: Category[];
  onClose: () => void;
  onSaved: (categoryId: string, list: ShoppingList) => void;
}) {
  const [category, setCategoryId] = useState(product.category_id);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const t = useT();

  async function save() {
    setBusy(true);
    setProblem("");
    try {
      onSaved(category, await setCategory(product.id, category, product.name));
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("common.save_failed"));
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={product.name}
      onClose={onClose}
      action={{
        label: busy ? t("common.saving") : t("common.save"),
        onClick: () => void save(),
        disabled: busy || category === product.category_id,
      }}
    >
      <Hint>{summary(t, product)}</Hint>
      <ChoiceChips
        label={t("item.section")}
        value={category}
        onChange={setCategoryId}
        options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${sectionName(t, one.id, one.name)}` }))}
      />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
    </Sheet>
  );
}

export function summary(t: Translate, product: Pick<Product, "times" | "since" | "every">): string {
  const bought = product.times === 1 ? t("product.bought_one") : t("product.bought_other", { count: product.times });
  const said = product.since ? t("product.last", { bought, since: product.since }) : t("product.plain", { bought });
  const every = product.every ? t("product.every", { every: product.every }) : t("product.unknown");
  return `${said} ${every}`;
}

function overdue(product: Pick<Product, "last" | "every_days">, today: string): number {
  const since = daysSince(product.last, today);
  if (since === null || !product.every_days) return -1;
  return since / product.every_days;
}

