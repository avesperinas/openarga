import { renderToString } from "react-dom/server";

import { route } from "./App";
import { budgetLine, calendarLine, landsIn, mailLine, removeConsequence, RenameSheet, runLine } from "./Connection";
import { AddSheet, missing } from "./Add";
import type { ConnectionDetail, Provider, Run } from "./api";
import { matching, oneAtATime } from "./BankSheet";

const run = (overrides: Partial<Run>): Run => ({
  operation: "holdings",
  started_at: "2026-09-22T05:00:00Z",
  finished_at: "2026-09-22T05:00:02Z",
  outcome: "ok",
  emitted: 0,
  detail: null,
  ...overrides,
});

test("cada pasada dice cómo fue, y un fallo con las palabras de la fuente", () => {
  expect(runLine(run({ emitted: 3 }))).toBe("Bien, 3 datos nuevos");
  expect(runLine(run({ emitted: 1 }))).toBe("Bien, 1 dato nuevo");
  expect(runLine(run({}))).toBe("Bien, sin nada nuevo");
  expect(runLine(run({ outcome: "error", detail: "Bitvavo 403 305: No active API key." }))).toBe(
    "Falló: Bitvavo 403 305: No active API key.",
  );
  expect(runLine(run({ outcome: "rate_limited" }))).toBe("La fuente pidió esperar");
  expect(runLine(run({ outcome: "running", finished_at: null }))).toBe("En marcha");
  expect(runLine(run({ operation: "search" }))).toBe("Contestó");
  expect(runLine(run({ operation: "run", detail: "Hecho en 4 turnos con claude-opus-5-5. Listo" }))).toBe(
    "Hecho en 4 turnos con claude-opus-5-5. Listo",
  );
});

test("quitar una conexión dice que lo ya traído se queda", () => {
  const connection = { provider_name: "Bitvavo" } as ConnectionDetail;

  expect(removeConsequence(connection)).toContain("Lo que ya trajo se queda en tus apps.");
});

test("quitar una cuenta de Claude dice que Chuping deja de lanzar sus pings", () => {
  const connection = { provider: "claude", provider_name: "Claude" } as ConnectionDetail;

  expect(removeConsequence(connection)).toContain("Chuping deja de lanzar sus pings");
});

test("cambiar el nombre parte del que tiene, y el de Claude dice para qué sirve", () => {
  const html = renderToString(
    <RenameSheet
      connection={{ id: "x", provider: "claude", provider_name: "Claude", label: "Trabajo" } as ConnectionDetail}
      onClose={() => undefined}
      onSaved={() => undefined}
    />,
  );

  expect(html).toContain("Cambiar nombre");
  expect(html).toContain('value="Trabajo"');
  expect(html).toContain("al pedirle a Claude que cambie su horario");
});

test("una conexión tiene su dirección, para recargar o llegar desde otra app", () => {
  const id = "0b7c2f1e-1b1a-4c55-9d1e-8a6f4a3c2b10";

  expect(route(`/hub/${id}`)).toEqual({ screen: "connection", id });
  expect(route("/hub/")).toEqual({ screen: "status" });
  expect(route("/hub/otra-cosa")).toEqual({ screen: "status" });
});

test("el estado y el catálogo son dos pestañas, cada una con su dirección", () => {
  expect(route("/hub")).toEqual({ screen: "status" });
  expect(route("/hub/configurar")).toEqual({ screen: "setup" });
  expect(route("/hub/configurar/")).toEqual({ screen: "setup" });
});

test("no se conecta hasta tener todo lo que pide", () => {
  const bitvavo = {
    secrets: [
      { key: "api_key", label: "Clave de API", help: "", multiline: false },
      { key: "api_secret", label: "Secreto", help: "", multiline: false },
    ],
  } as Provider;

  expect(missing(bitvavo, { api_key: "abc" })).toEqual(["Secreto"]);
  expect(missing(bitvavo, { api_key: "abc", api_secret: "  " })).toEqual(["Secreto"]);
  expect(missing(bitvavo, { api_key: "abc", api_secret: "def" })).toEqual([]);
});

test("la hoja de añadir dice dónde se consigue cada cosa y no enseña lo pegado", () => {
  const html = renderToString(
    <AddSheet
      provider={{
        id: "bitvavo",
        name: "Bitvavo",
        description: "Tu cripto.",
        capabilities: ["sync"],
        available: true,
        single: true,
        lives_in: null,
        secrets: [{ key: "api_key", label: "Clave de API", help: "En Bitvavo, Ajustes → API.", multiline: false }],
      }}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );

  expect(html).toContain("Conectar Bitvavo");
  expect(html).toContain("En Bitvavo, Ajustes → API.");
  expect(html).toContain('type="password"');
});

test("los accesos del día se dicen, y cuando no queda ninguno también", () => {

  expect(budgetLine({ limit: 4, used: 1, remaining: 3 })).toBe("Quedan 3 de 4 accesos hoy.");
  expect(budgetLine({ limit: 4, used: 4, remaining: 0 })).toContain("ya no quedan accesos");
});

test("la lista de bancos se busca sin tildes ni mayúsculas, y un toque doble no abre dos", () => {
  let calls = 0;
  const once = oneAtATime(() => {
    calls += 1;
    return new Promise<string>(() => undefined);
  });

  expect(matching(["Banco Inventado", "Caja Rural", "Ibercaja"], "CAJA")).toEqual(["Caja Rural", "Ibercaja"]);
  expect(matching(["Banco Añil"], "anil")).toEqual(["Banco Añil"]);
  expect(once()).not.toBeNull();
  expect(once()).toBeNull();
  expect(calls).toBe(1);
});

test("un buzón dice qué entidades lee, o que aún ninguna", () => {

  expect(mailLine([])).toContain("Todavía no lee ninguna entidad");
  expect(mailLine([{ entity: "Gestora Inventada" }])).toBe(
    "Lee los correos de Gestora Inventada. Los demás no se abren.",
  );
});

test("una suscripción de calendario dice qué trae con sus parámetros", () => {

  expect(calendarLine({ provider: "holidays", settings: { country: "ES", region: "ES-NC" } })).toBe(
    "Los festivos nacionales de ES y los de ES-NC.",
  );
  expect(calendarLine({ provider: "formula1", settings: { sessions: ["race", "qualifying", "sprint"] } })).toBe(
    "Cada Gran Premio con la carrera, la clasificación y el sprint.",
  );
  expect(calendarLine({ provider: "ical", settings: { url: "https://example.org/equipo.ics" } })).toBe(
    "El calendario de example.org, cada día.",
  );
  expect(calendarLine({ provider: "football", settings: { team: "11", team_name: "Equipo de prueba" } })).toBe(
    "Los partidos de Equipo de prueba: liga, copa y Europa, cada seis horas.",
  );
  expect(calendarLine({ provider: "imap", settings: {} })).toBeNull();
});

test("una conexión dice a qué apps llega por las tomas que declaran, sin nombrarlas aquí", () => {

  expect(landsIn({ inlets: [] })).toBeNull();
  expect(landsIn({ inlets: [{ key: "planner.calendar", app: "Planner", title: "Calendario", settings: [] }] })).toBe("Llega a Planner.");
  expect(
    landsIn({
      inlets: [
        { key: "money.accounts", app: "Money", title: "Cuentas", settings: [] },
        { key: "carrera.movements", app: "Carrera", title: "Movimientos", settings: [] },
      ],
    }),
  ).toBe("Llega a Money y Carrera.");
});
