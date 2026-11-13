import { TextField } from "@openarga/ui";
import { useState } from "react";

import type { Edition } from "./api";
import { splitAuthors } from "./words";
import { t } from "./lang";

export function EditionFields({ edition, onChange }: { edition: Edition; onChange: (edition: Edition) => void }) {
  const [authors, setAuthors] = useState(edition.authors.join(", "));
  const set = (changes: Partial<Edition>) => onChange({ ...edition, ...changes });
  const number = (text: string) => (text.trim() && /^\d+$/.test(text.trim()) ? Number(text.trim()) : null);

  return (
    <div className="library-fields">
      <TextField label={t("edition.title")} value={edition.title} onChange={(title) => set({ title })} autoFocus />
      <TextField
        label={t("edition.authors")}
        value={authors}
        placeholder={t("edition.authors_hint")}
        onChange={(text) => {
          setAuthors(text);
          set({ authors: splitAuthors(text) });
        }}
      />
      <div className="library-dates">
        <TextField
          label={t("edition.pages_label")}
          inputMode="numeric"
          value={edition.pages?.toString() ?? ""}
          onChange={(text) => set({ pages: number(text) })}
        />
        <TextField
          label={t("edition.year")}
          inputMode="numeric"
          value={edition.year?.toString() ?? ""}
          onChange={(text) => set({ year: number(text) })}
        />
      </div>
      <div className="library-dates">
        <TextField
          label={t("edition.language")}
          placeholder="es, en, eu…"
          value={edition.language ?? ""}
          onChange={(text) => set({ language: text.trim().toLowerCase() || null })}
        />
        <TextField label="ISBN" inputMode="numeric" value={edition.isbn ?? ""} onChange={(isbn) => set({ isbn: isbn || null })} />
      </div>
    </div>
  );
}
