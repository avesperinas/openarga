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
import { dayLabel, daysSince, habitDetail } from "./words";

export function HistoryScreen({ onList }: { onList: () => void }) {
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
      <ScreenHeader title="Historial" />
      <OfflineNotice />

      {done.error && trips === null && (
        <ErrorState title="No se ha podido leer el historial" detail={done.error.message} onRetry={done.refresh} />
      )}
      {done.loading && <Skeleton label="Cargando el historial" />}

      {trips !== null && trips.length === 0 && (
        <EmptyState
          icon="calendar"
          title="Todavía no hay compras"
          action={{ label: "Ir a la lista", icon: "basket", onClick: onList }}
        >
          Cuando termines una, se guarda aquí con su fecha. Con tres compras de algo, Shopping sabe cada cuánto lo
          compras y te avisa cuando te toca.
        </EmptyState>
      )}

      {trips && trips.length > 0 && (
        <Section title="Compras" count={trips.length}>
          <List>
            {trips.map((one) => (
              <ListRow
                key={one.id}
                title={dayLabel(one.finished_at)}
                detail={one.items === 1 ? "1 producto" : `${one.items} productos`}
                accessory="chevron-right"
                onClick={() => setTrip(one)}
              />
            ))}
          </List>
        </Section>
      )}

      {bought.length > 0 && (
        <Section title="Lo que compras">
          <FrequencyRows label="Lo que compras">
            {byOverdue.map((one) => {
              const since = daysSince(one.last, today);
              return (
                <FrequencyRow
                  key={one.id}
                  title={one.name}
                  since={since}
                  every={one.every_days}
                  label={`${one.name}: ${habitDetail(one)}`}
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

  async function save() {
    setBusy(true);
    setProblem("");
    try {
      onSaved(category, await setCategory(product.id, category, product.name));
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={product.name}
      onClose={onClose}
      action={{
        label: busy ? "Guardando…" : "Guardar",
        onClick: () => void save(),
        disabled: busy || category === product.category_id,
      }}
    >
      <Hint>{summary(product)}</Hint>
      <ChoiceChips
        label="Sección"
        value={category}
        onChange={setCategoryId}
        options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${one.name}` }))}
      />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
    </Sheet>
  );
}

export function summary(product: Pick<Product, "times" | "since" | "every">): string {
  const times = product.times === 1 ? "una vez" : `${product.times} veces`;
  const last = product.since ? `, la última ${product.since}` : "";
  const every = product.every
    ? ` Lo compras ${product.every}.`
    : " Con tres compras se sabrá cada cuánto lo compras.";
  return `Comprado ${times}${last}.${every}`;
}

function overdue(product: Pick<Product, "last" | "every_days">, today: string): number {
  const since = daysSince(product.last, today);
  if (since === null || !product.every_days) return -1;
  return since / product.every_days;
}

