import { renderToString } from "react-dom/server";

import { ByApp, ProviderSection, Yours, appPath, providerAction, providersOf, whereItLives } from "./Home";
import type { Connection, Provider } from "./api";

const provider = (overrides: Partial<Provider>): Provider => ({
  id: "bitvavo",
  name: "Bitvavo",
  description: "",
  capabilities: ["sync"],
  available: false,
  single: false,
  lives_in: null,
  secrets: [],
  ...overrides,
});

const connection = (overrides: Partial<Connection>): Connection => ({
  id: "c1",
  provider: "bitvavo",
  label: "Bitvavo",
  category: "finance",
  state: "active",
  brief: "Al día",
  tone: "positive",
  reason: null,
  last_ok_at: null,
  emitted_week: 0,
  ...overrides,
});

test("lo que aún se configura en su app lo dice y lleva hasta allí", () => {
  const bitvavo = provider({ lives_in: "Money" });

  expect(whereItLives(bitvavo)).toBe("En Money");
  expect(appPath(bitvavo)).toBe("/money");
});

test("el nombre de la app con tilde lleva a su ruta sin ella", () => {
  expect(appPath(provider({ lives_in: "Recipes" }))).toBe("/recipes");
});

test("lo que no existe en ningún sitio todavía no finge estar", () => {
  const mail = provider({ id: "imap", name: "Correo" });

  expect(whereItLives(mail)).toBe("Próximamente");
  expect(appPath(mail)).toBeNull();
});

test("sin nada conectado se explica qué es esto, no se enseña una lista vacía", () => {
  const html = renderToString(<Yours connections={[]} />);

  expect(html).toContain("Nada conectado aquí todavía");
  expect(html).toContain("sin que tengas que");
});

test("una conexión que pide algo dice qué, con su nombre", () => {
  const html = renderToString(
    <Yours
      connections={[
        {
          id: "1",
          provider: "enable_banking",
          label: "BBVA",
          category: "finance",
          state: "expiring",
          brief: "Por caducar",
          tone: "warning",
          reason: "El acceso a BBVA caduca en 3 días.",
          last_ok_at: null,
          emitted_week: 0,
        },
      ]}
    />,
  );

  expect(html).toContain("Por caducar");
  expect(html).toContain('data-tone="warning"');
  expect(html).toContain("El acceso a BBVA caduca en 3 días.");
});

test("cada trozo enseña sus proveedores y dónde están", () => {
  const html = renderToString(
    <ProviderSection
      title="Otras fuentes"
      providers={[provider({ lives_in: "Money" }), provider({ id: "imap", name: "Correo" })]}
    />,
  );

  expect(html).toContain("Otras fuentes");
  expect(html).toContain("En Money");
  expect(html).toContain("Próximamente");
});

test("lo que ya está en el hub se añade aquí", () => {
  const bitvavo = provider({ available: true, single: true });

  expect(whereItLives(bitvavo)).toBe("Añadir");
  expect(providerAction(bitvavo, [])).toEqual({ kind: "add" });
});

test("lo que se tiene una vez y ya está conectado abre su ficha en vez de añadir otro", () => {
  const bitvavo = provider({ available: true, single: true });

  expect(whereItLives(bitvavo, true)).toBe("Conectado");
  expect(providerAction(bitvavo, [connection({ id: "c9" })])).toEqual({ kind: "open", id: "c9" });
});

test("lo que aún vive en su app lleva allí, y lo que no existe no hace nada", () => {
  expect(providerAction(provider({ lives_in: "Money" }), [])).toEqual({ kind: "app", path: "/money" });
  expect(providerAction(provider({ id: "imap" }), [])).toBeNull();
});

test("lo que crea otra app se ve aquí pero se añade allí: una cuenta de Claude, desde Chuping", () => {
  const claude = provider({ id: "claude", available: true, created_in: "Chuping" });

  expect(whereItLives(claude)).toBe("Desde Chuping");
  expect(providerAction(claude, [])).toEqual({ kind: "app", path: "/chuping" });
});

test("una entidad que se lee por correo sale en su categoría con esa marca", () => {
  expect(whereItLives(provider({ id: "imap.gestora", name: "Gestora", by_mail: true }))).toBe("Por correo");
});

test("en Configurar se ven las cuentas que ya tienes, y debajo la fila para añadir otra", () => {
  const html = renderToString(
    <ProviderSection
      title="Chuping"
      providers={[provider({ id: "claude", name: "Claude", available: true })]}
      connections={[
        connection({ id: "c1", provider: "claude", label: "Personal" }),
        connection({ id: "c2", provider: "claude", label: "Trabajo", brief: "Caducada", tone: "negative" }),
        connection({ id: "c3", provider: "bitvavo", label: "Bitvavo" }),
      ]}
    />,
  );

  expect(html).toContain("Personal");
  expect(html).toContain("Trabajo");
  expect(html).toContain('data-tone="negative"');
  expect(html).not.toContain("Bitvavo");
  expect(html.indexOf("Trabajo")).toBeLessThan(html.indexOf("Añadir"));
});

test("lo que se tiene una vez y ya está conectado es solo su conexión, sin fila de añadir", () => {
  const html = renderToString(
    <ProviderSection
      title="Money"
      providers={[provider({ available: true, single: true })]}
      connections={[connection({ label: "Mi Bitvavo" })]}
    />,
  );

  expect(html).toContain("Mi Bitvavo");
  expect(html).toContain("Al día");
  expect(html).not.toContain("Añadir");
});

describe("por app (ADR-0103)", () => {
  const catalogue = [
    {
      id: "finance",
      name: "Finanzas",
      providers: [
        provider({ id: "enable_banking", name: "Bancos (PSD2)", available: true }),
        provider({ id: "imap", name: "Correo", available: true }),
        provider({ id: "imap.gestora", name: "Gestora", by_mail: true }),
      ],
    },
    { id: "books", name: "Libros", providers: [provider({ id: "openlibrary", name: "Open Library", available: true })] },
    { id: "economy", name: "Economía", providers: [provider({ id: "ine", name: "INE", available: true })] },
  ];
  const apps = {
    apps: [
      {
        module: "money",
        name: "Money",
        view: "/money",
        inlets: [{ key: "money.accounts", title: "Cuentas", providers: ["enable_banking", "imap"] }],
        services: [],
      },
      {
        module: "library",
        name: "Library",
        view: "/library",
        inlets: [],
        services: [{ provider: "openlibrary", capabilities: ["books.search"] }],
      },
    ],
    others: ["ine"],
  };

  it("lo que se lee por correo va detrás del buzón, en la app a la que llega", () => {
    expect(providersOf(["imap"], catalogue).map((one) => one.id)).toEqual(["imap", "imap.gestora"]);
  });

  it("cada app con lo que le llega, sus conexiones encima, y aparte lo que no llega a ninguna", () => {
    const html = renderToString(
      <ByApp apps={apps} catalogue={catalogue} connections={[connection({ id: "b1", provider: "enable_banking", label: "Banco de prueba" })]} />,
    );

    expect(html).toContain("Money");
    expect(html).toContain("Banco de prueba");
    expect(html).toContain("Gestora");
    expect(html).toContain("Library");
    expect(html).toContain("Open Library");
    expect(html.indexOf("Library")).toBeLessThan(html.indexOf("Otras fuentes"));
    expect(html).toContain("INE");
    expect(html.indexOf("Money")).toBeLessThan(html.indexOf("Banco de prueba"));
  });
});
