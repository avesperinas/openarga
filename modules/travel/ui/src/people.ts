import { useEffect, useState } from "react";

import { type Traveller, readSpaces } from "./api";
import { t } from "./lang";

export type Members = Map<string, string>;

const OWNER = new Set(["Me", "Yo"]);

export function travellerLabel(one: Traveller, members: Members): string {
  if (one.me) return t("people.you");
  const member = one.member_user_id ? members.get(one.member_user_id) : undefined;
  if (OWNER.has(one.name)) return member ?? t("people.owner");
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
        setMembers(new Map((space?.members ?? []).map((one) => [one.user_id, one.name ?? t("share.no_name")])));
      })
      .catch(() => setMembers(new Map()));
  }, [spaceId]);
  return members;
}
