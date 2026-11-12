import { describe, expect, it } from "vitest";

import { envelopeKey, identity, launchable, type ModuleSummary, serviceUrl, widgetUrl } from "./kernel";

describe("a quién se le pide el dato de un widget", () => {
  it("los del kernel van al kernel", () => {
    expect(serviceUrl("/api/kernel/widgets/events")).toBe("http://kernel:8000/widgets/events");
  });

  it("los de un módulo van a su servicio, que se llama como el módulo", () => {
    expect(serviceUrl("/api/training/widgets/week")).toBe("http://training:8000/widgets/week");
  });

  it("un endpoint que no cuelga de /api/<módulo> no se traduce a un host cualquiera", () => {
    expect(() => serviceUrl("/widgets/main")).toThrow();
    expect(() => serviceUrl("/api/Demo/widgets/main")).toThrow();
    expect(() => serviceUrl("http://otro-sitio/widgets/main")).toThrow();
  });
});

describe("qué enseña el lanzador", () => {
  it("solo los módulos habilitados: uno renombrado o retirado no lleva a una app que ya no existe", () => {
    const module = (id: string, enabled: boolean): ModuleSummary => ({
      id,
      name: id,
      version: "0.1.0",
      enabled,
      api_prefix: `/api/${id}`,
      view: `/${id}`,
      scopes: [],
      updated_at: "2026-09-17T08:00:00Z",
    });

    expect(launchable([module("travel", false), module("library", true)]).map((m) => m.id)).toEqual(["library"]);
  });
});

describe("quién mira, cuando la shell pide desde el servidor", () => {
  it("reenvía el sub y la persona que inyectó el gateway, y nada más", () => {
    const incoming = new Headers({
      "x-arga-subject": "sub-sintetico",
      "x-arga-user": "00000000-0000-4000-8000-00000000a7e5",
      cookie: "no-se-reenvia=1",
    });

    expect(identity(incoming)).toEqual({
      "x-arga-subject": "sub-sintetico",
      "x-arga-user": "00000000-0000-4000-8000-00000000a7e5",
    });
  });

  it("reenvía también sus espacios, para que lo compartido llegue en la primera carga", () => {
    const spaces = "00000000-0000-4000-8000-0000000005a1,00000000-0000-4000-8000-0000000005a2";
    const incoming = new Headers({
      "x-arga-subject": "sub-sintetico",
      "x-arga-user": "00000000-0000-4000-8000-00000000a7e5",
      "x-arga-spaces": spaces,
    });

    expect(identity(incoming)["x-arga-spaces"]).toBe(spaces);
  });

  it("sin cabeceras no inventa a nadie", () => {
    expect(identity(new Headers())).toEqual({});
  });
});

describe("un widget que pregunta algo al ponerlo (ADR-0099)", () => {
  it("cada elección es su propio sobre, y viaja en la dirección", () => {
    expect(envelopeKey("money", "account", "renault")).toBe("money/account?renault");
    expect(envelopeKey("money", "account", null)).toBe("money/account");
    expect(widgetUrl("/api/money/widgets/v1_account", "cuenta a")).toBe("/api/money/widgets/v1_account?option=cuenta%20a");
    expect(widgetUrl("/api/money/widgets/v1_account", undefined)).toBe("/api/money/widgets/v1_account");
  });
});

