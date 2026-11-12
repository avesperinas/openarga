type Here = Pick<Location, "pathname" | "search" | "assign">;

export function signIn(here: Here = globalThis.location): void {
  here.assign(`/login?next=${encodeURIComponent(here.pathname + here.search)}`);
}

export async function request(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401) signIn();
  return response;
}
