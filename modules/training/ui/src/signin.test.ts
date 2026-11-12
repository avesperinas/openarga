import { signIn } from "./api";

describe("la sesión de arga caducada", () => {
  it("lleva a entrar y vuelve a la misma pantalla de Training", () => {
    const assigned: string[] = [];
    signIn({ pathname: "/training/sesion/42", search: "", assign: (url) => void assigned.push(String(url)) });

    expect(assigned).toEqual(["/login?next=%2Ftraining%2Fsesion%2F42"]);
  });
});
