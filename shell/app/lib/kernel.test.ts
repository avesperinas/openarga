import { describe, expect, it } from "vitest";

import { envelopeKey, identity, launchable, type ModuleSummary, serviceUrl, widgetUrl } from "./kernel";

describe("whom a widget's data is requested from", () => {
  it("the kernel's go to the kernel", () => {
    expect(serviceUrl("/api/kernel/widgets/events")).toBe("http://kernel:8000/widgets/events");
  });

  it("a module's go to its service, named like the module", () => {
    expect(serviceUrl("/api/training/widgets/week")).toBe("http://training:8000/widgets/week");
  });

  it("an endpoint outside /api/<module> is not turned into an arbitrary host", () => {
    expect(() => serviceUrl("/widgets/main")).toThrow();
    expect(() => serviceUrl("/api/Demo/widgets/main")).toThrow();
    expect(() => serviceUrl("http://otro-sitio/widgets/main")).toThrow();
  });
});

describe("what the launcher shows", () => {
  it("only enabled modules: a renamed or retired one does not lead to an app that no longer exists", () => {
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
    expect(launchable([module("study", true), module("library", true)], ["study"]).map((m) => m.id)).toEqual(["library"]);
  });
});

describe("who is looking, when the shell requests from the server", () => {
  it("forwards the sub and the person the gateway injected, and nothing else", () => {
    const incoming = new Headers({
      "x-arga-subject": "sub-sintetico",
      "x-arga-user": "00000000-0000-4000-8000-00000000a7e5",
      cookie: "not-forwarded=1",
    });

    expect(identity(incoming)).toEqual({
      "x-arga-subject": "sub-sintetico",
      "x-arga-user": "00000000-0000-4000-8000-00000000a7e5",
    });
  });

  it("also forwards their spaces, so shared data arrives on the first load", () => {
    const spaces = "00000000-0000-4000-8000-0000000005a1,00000000-0000-4000-8000-0000000005a2";
    const incoming = new Headers({
      "x-arga-subject": "sub-sintetico",
      "x-arga-user": "00000000-0000-4000-8000-00000000a7e5",
      "x-arga-spaces": spaces,
    });

    expect(identity(incoming)["x-arga-spaces"]).toBe(spaces);
  });

  it("also forwards their language, so the names of the apps arrive in it", () => {
    const incoming = new Headers({ "x-arga-subject": "sub-sintetico", "x-arga-locale": "es" });

    expect(identity(incoming)["x-arga-locale"]).toBe("es");
  });

  it("without headers it invents nobody", () => {
    expect(identity(new Headers())).toEqual({});
  });
});

describe("a widget that asks something when placed (ADR-0099)", () => {
  it("each choice is its own envelope, and travels in the address", () => {
    expect(envelopeKey("money", "account", "renault")).toBe("money/account?renault");
    expect(envelopeKey("money", "account", null)).toBe("money/account");
    expect(widgetUrl("/api/money/widgets/v1_account", "cuenta a")).toBe("/api/money/widgets/v1_account?option=cuenta%20a");
    expect(widgetUrl("/api/money/widgets/v1_account", undefined)).toBe("/api/money/widgets/v1_account");
  });
});

