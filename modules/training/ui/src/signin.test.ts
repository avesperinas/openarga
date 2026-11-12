import { signIn } from "./api";

describe("an expired arga session", () => {
  it("leads to sign in and comes back to the same Training screen", () => {
    const assigned: string[] = [];
    signIn({ pathname: "/training/session/42", search: "", assign: (url) => void assigned.push(String(url)) });

    expect(assigned).toEqual(["/login?next=%2Ftraining%2Fsession%2F42"]);
  });
});
