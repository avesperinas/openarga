import { DataTable, Hint, List, Section, SegmentedControl, ShareChart, type TableColumn } from "@openarga/ui";
import { useState } from "react";

import { Loading, dayText, useLoad } from "./analysisParts";
import { type AnalysisQuery, type Composition, api } from "./api";
import { moneyWhole } from "./format";
import { FundListRow } from "./Products";

type By = "asset" | "region" | "fund" | "product";

const BY: { value: By; label: string }[] = [
  { value: "asset", label: "Activo" },
  { value: "region", label: "Región" },
  { value: "fund", label: "Fondo" },
  { value: "product", label: "Producto" },
];

const WHAT: Record<By, string> = {
  asset: "Qué parte de la cartera es renta variable, renta fija, inmobiliario, liquidez o cripto",
  region: "Dónde está invertida la cartera, por regiones",
  fund: "Qué parte de la cartera es cada fondo, sumando el mismo fondo en varios productos",
  product: "Qué parte de la cartera es cada producto",
};

function items(c: Composition, by: By) {
  if (by === "asset") return c.by_asset;
  if (by === "region") return c.by_region;
  if (by === "fund") return c.by_fund;
  return c.by_product;
}

export function CompositionSection({ q, picked }: { q: AnalysisQuery; picked: string | null }) {
  const state = useLoad(() => api.composition(q), JSON.stringify(q));
  const [by, setBy] = useState<By>("asset");
  return (
    <Loading state={state} rows={4}>
      {(c) => {
        const shown = items(c, by);
        const product = picked ? c.products.find((p) => p.key === picked) : undefined;
        const unknown = by === "asset" ? c.unknown_asset : by === "region" ? c.unknown_region : 0;
        const fundColumns: TableColumn<Composition["by_fund"][number]>[] = [
          { key: "name", label: "Fondo", cell: (f) => f.name },
          { key: "products", label: "En", cell: (f) => f.products.join(", ") },
          { key: "value", label: "Valor", numeric: true, cell: (f) => moneyWhole(f.value) },
          {
            key: "share",
            label: "Peso",
            numeric: true,
            cell: (f) => `${c.total ? Math.round((f.value / c.total) * 1000) / 10 : 0} %`.replace(".", ","),
          },
        ];
        return (
          <>
            <Section title={`Composición a ${dayText(c.on)}`}>
              <SegmentedControl<By> label="Repartir por" value={by} onChange={setBy} options={BY} />
              <ShareChart label={WHAT[by]} items={shown} order={shown.map((s) => s.key)} format={(v) => moneyWhole(v)} />
              {unknown > 0 && (
                <Hint>
                  {moneyWhole(unknown)} sin desglose: productos de los que no se sabe en qué fondos están, o fondos sin clasificar. Se
                  apuntan en Ajustes › Cuentas y productos.
                </Hint>
              )}
              {by === "fund" && c.by_fund.length > 0 && (
                <DataTable label="Cada fondo, en qué productos está y cuánto pesa" columns={fundColumns} rows={c.by_fund} rowKey={(f) => f.key} />
              )}
            </Section>
            {product && (
              <Section title={product.on ? `Fondos de ${product.name} · foto del ${dayText(product.on)}` : `Fondos de ${product.name}`}>
                {product.funds.length > 0 ? (
                  <List>
                    {product.funds.map((f) => (
                      <FundListRow key={f.symbol} fund={f} />
                    ))}
                  </List>
                ) : (
                  <Hint>No se sabe en qué fondos está: apúntalo en su ficha, en Ajustes › Cuentas y productos.</Hint>
                )}
                {product.funds.length > 0 && <Hint>Cada fondo, por lo que vale hoy: el de su foto, movido con su precio.</Hint>}
              </Section>
            )}
          </>
        );
      }}
    </Loading>
  );
}
