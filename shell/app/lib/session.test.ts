import { describe, expect, it, vi } from "vitest";

import { request, signIn } from "./session";

function here(pathname: string, search = "") {
  const assigned: string[] = [];
  return { pathname, search, assign: (url: string | URL) => void assigned.push(String(url)), assigned };
}

describe("la sesión caducada", () => {
  it("lleva a entrar y vuelve a la misma pantalla", () => {
    const location = here("/training/hoy", "?semana=3");

    signIn(location);

    expect(location.assigned).toEqual(["/login?next=%2Ftraining%2Fhoy%3Fsemana%3D3"]);
  });

  it("una respuesta 401 lleva a entrar y las demás no", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/", search: "", assign });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response("{}", { status: url === "/fuera" ? 401 : 200 })));

    const ok = await request("/dentro");
    expect(assign).not.toHaveBeenCalled();
    const out = await request("/fuera");

    expect(ok.status).toBe(200);
    expect(out.status).toBe(401);
    expect(assign).toHaveBeenCalledWith("/login?next=%2F");
    vi.unstubAllGlobals();
  });
});
