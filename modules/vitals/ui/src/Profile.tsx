import { Heading } from "@openarga/ui";
import type { Profile } from "./api";
import { profileRows } from "./body";

export function ProfileCard({ profile, medications = true }: { profile: Profile | null; medications?: boolean }) {
  const rows = profile ? profileRows(profile, medications) : [];
  if (rows.length === 0) return null;
  return (
    <section className="surface vitals-card" aria-label="Ficha">
      <Heading>Ficha</Heading>
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
