import { DataTable, Hint, List, Section, SegmentedControl, ShareChart, type TableColumn, useT } from "@openarga/ui";
import { useState } from "react";

import { Loading, dayText, useLoad } from "./analysisParts";
import { type AnalysisQuery, type Composition, api } from "./api";
import { moneyWhole, percentText } from "./format";
import { FundListRow } from "./Products";

type By = "asset" | "region" | "fund" | "product";

const BY: By[] = ["asset", "region", "fund", "product"];

function items(c: Composition, by: By) {
  if (by === "asset") return c.by_asset;
  if (by === "region") return c.by_region;
  if (by === "fund") return c.by_fund;
  return c.by_product;
}

export function CompositionSection({ q, picked }: { q: AnalysisQuery; picked: string | null }) {
  const state = useLoad(() => api.composition(q), JSON.stringify(q));
  const t = useT();
  const [by, setBy] = useState<By>("asset");
  return (
    <Loading state={state} rows={4}>
      {(c) => {
        const shown = items(c, by);
        const product = picked ? c.products.find((p) => p.key === picked) : undefined;
        const unknown = by === "asset" ? c.unknown_asset : by === "region" ? c.unknown_region : 0;
        const fundColumns: TableColumn<Composition["by_fund"][number]>[] = [
          { key: "name", label: t("composition.by_fund"), cell: (f) => f.name },
          { key: "products", label: t("composition.in"), cell: (f) => f.products.join(", ") },
          { key: "value", label: t("composition.value"), numeric: true, cell: (f) => moneyWhole(f.value) },
          {
            key: "share",
            label: t("composition.weight"),
            numeric: true,
            cell: (f) => percentText(c.total ? f.value / c.total : 0),
          },
        ];
        return (
          <>
            <Section title={t("composition.on", { day: dayText(c.on) })}>
              <SegmentedControl<By> label={t("composition.split_by")} value={by} onChange={setBy} options={BY.map((value) => ({ value, label: t(`composition.by_${value}`) }))} />
              <ShareChart label={t(`composition.what_${by}`)} items={shown} order={shown.map((s) => s.key)} format={(v) => moneyWhole(v)} />
              {unknown > 0 && (
                <Hint>{t("composition.unknown", { amount: moneyWhole(unknown) })}</Hint>
              )}
              {by === "fund" && c.by_fund.length > 0 && (
                <DataTable label={t("composition.table")} columns={fundColumns} rows={c.by_fund} rowKey={(f) => f.key} />
              )}
            </Section>
            {product && (
              <Section
                title={
                  product.on
                    ? t("product.funds_of_on", { name: product.name, day: dayText(product.on) })
                    : t("product.funds_of", { name: product.name })
                }
              >
                {product.funds.length > 0 ? (
                  <List>
                    {product.funds.map((f) => (
                      <FundListRow key={f.symbol} fund={f} />
                    ))}
                  </List>
                ) : (
                  <Hint>{t("product.funds_unknown")}</Hint>
                )}
                {product.funds.length > 0 && <Hint>{t("product.funds_hint")}</Hint>}
              </Section>
            )}
          </>
        );
      }}
    </Loading>
  );
}
