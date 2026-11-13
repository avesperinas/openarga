import { Heading, useLocale, useT } from "@openarga/ui";

import type { Profile } from "./api";
import { profileRows } from "./body";

export function ProfileCard({ profile, medications = true }: { profile: Profile | null; medications?: boolean }) {
  const t = useT();
  const locale = useLocale();
  const rows = profile ? profileRows(profile, t, locale, medications) : [];
  if (rows.length === 0) return null;
  return (
    <section className="surface vitals-card" aria-label={t("profile.title")}>
      <Heading>{t("profile.title")}</Heading>
      <dl className="vitals-profile">
        {rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
