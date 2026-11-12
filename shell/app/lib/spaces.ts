import { request } from "./session";

export interface SpaceMember {
  user_id: string;
  role: "owner" | "member";
  name: string | null;
}

export interface Space {
  id: string;
  name: string;
  role: "owner" | "member";
  me: string;
  members: SpaceMember[];
}

export interface Invite {
  code: string;
  expires_at: string;
}

const BASE = "/api/kernel/spaces";

export class SpaceError extends Error {}

async function call<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const response = await request(`${BASE}${path}`, {
    ...rest,
    headers: json === undefined ? undefined : { "content-type": "application/json" },
    body: json === undefined ? undefined : JSON.stringify(json),
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    throw new SpaceError(detail ?? "No se ha podido hacer. Prueba otra vez en un momento.");
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const readSpaces = () => call<Space[]>("");
export const createSpace = (name: string, me: string) =>
  call<Space>("", { method: "POST", json: { name: name.trim(), me: me.trim() } });
export const joinSpace = (code: string, me: string) =>
  call<Space>("/join", { method: "POST", json: { code: code.trim(), me: me.trim() } });
export const inviteTo = (space: string) => call<Invite>(`/${space}/invites`, { method: "POST" });
export const renameMe = (space: string, name: string) =>
  call<Space>(`/${space}/me`, { method: "PUT", json: { name: name.trim() } });
export const removeMember = (space: string, member: string) =>
  call<void>(`/${space}/members/${member}`, { method: "DELETE" });

export function memberLabel(space: Space, member: SpaceMember): string {
  if (member.user_id === space.me) return "Tú";
  return member.name ?? "Sin nombre";
}

export function membersLine(space: Space): string {
  if (space.members.length === 1) return "Solo tú, de momento";
  const others = space.members.filter((member) => member.user_id !== space.me);
  const names = ["Tú", ...others.map((member) => member.name ?? "Sin nombre")];
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`;
}

export function myName(space: Space): string {
  return space.members.find((member) => member.user_id === space.me)?.name ?? "";
}

export const looksLikeCode = (code: string) => code.replace(/[^a-z0-9]/gi, "").length >= 12;
