import { useEffect, useState } from "react";

import { type Traveller, readSpaces } from "./api";

export type Members = Map<string, string>;

export function travellerLabel(one: Traveller, members: Members): string {
  if (one.me) return "Tú";
  const member = one.member_user_id ? members.get(one.member_user_id) : undefined;
  if (one.name === "Yo") return member ?? "Quien creó el viaje";
  return one.name;
}

export function useMembers(spaceId: string | null): Members {
  const [members, setMembers] = useState<Members>(new Map());
  useEffect(() => {
    if (!spaceId) {
      setMembers(new Map());
      return;
    }
    readSpaces()
      .then((spaces) => {
        const space = spaces.find((one) => one.id === spaceId);
        setMembers(new Map((space?.members ?? []).map((one) => [one.user_id, one.name ?? "Sin nombre"])));
      })
      .catch(() => setMembers(new Map()));
  }, [spaceId]);
  return members;
}
