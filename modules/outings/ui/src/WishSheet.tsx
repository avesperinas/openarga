import { Button, ChoiceChips, Hint, ListRow, Photo, Sheet, TextField } from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import {
  type Kind,
  type Place,
  type Wish,
  addWish,
  photoUrl,
  removePhoto,
  updateWish,
  uploadPhoto,
} from "./api";
import { t } from "./lang";
import { shrink } from "./photo";
import { PlacePicker } from "./PlacePicker";
import { kindOf, kinds, placeLine, placeholders } from "./words";

type Photo = { kind: "kept" } | { kind: "new"; blob: Blob; url: string } | { kind: "none" };

export function WishSheet({
  wish,
  initialKind = "getaway",
  onClose,
  onSaved,
  onError,
}: {
  wish?: Wish;
  initialKind?: Kind;
  onClose: () => void;
  onSaved: (wish: Wish) => void;
  onError: (error: unknown) => void;
}) {
  const [kind, setKind] = useState<Kind>(wish?.kind ?? initialKind);
  const [name, setName] = useState(wish?.name ?? "");
  const [body, setBody] = useState(wish?.body ?? "");
  const [place, setPlace] = useState<Place | null>(wish?.place ?? null);
  const [picking, setPicking] = useState(false);
  const [photo, setPhoto] = useState<Photo>(wish?.has_photo ? { kind: "kept" } : { kind: "none" });
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => void (photo.kind === "new" && URL.revokeObjectURL(photo.url)), [photo]);

  async function choose(file: File | undefined) {
    if (!file) return;
    setProblem("");
    try {
      const blob = await shrink(file);
      setPhoto({ kind: "new", blob, url: URL.createObjectURL(blob) });
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("problem.photo"));
    }
  }

  async function save() {
    if (!name.trim()) return;
    setSaving(true);
    setProblem("");
    const fields = { kind, name: name.trim(), body: body.trim() || null, place };
    try {
      let saved = wish ? await updateWish(wish.id, fields) : await addWish(fields);
      try {
        if (photo.kind === "new") saved = await uploadPhoto(saved.id, photo.blob);
        if (photo.kind === "none" && saved.has_photo) saved = await removePhoto(saved.id);
      } catch (error) {
        onSaved(saved);
        onError(new Error(t("problem.photo_after", { reason: error instanceof Error ? error.message : t("problem.failed") })));
        return;
      }
      onSaved(saved);
    } catch (error) {
      onError(error);
    } finally {
      setSaving(false);
    }
  }

  const shown = photo.kind === "new" ? photo.url : photo.kind === "kept" && wish ? photoUrl(wish) : undefined;
  const hints = placeholders(kind);

  return (
    <Sheet
      title={wish ? t("action.edit") : t("wishes.note")}
      onClose={onClose}
      action={{ label: saving ? t("action.saving") : t("action.save"), onClick: () => void save(), disabled: saving || !name.trim() }}
    >
      <div className="outings-fields">
        <Photo
          src={shown}
          hue={kindOf(kind).hue}
          icon={kindOf(kind).icon}
          shape="banner"
          loading="eager"
          action={{ label: shown ? t("photo.change") : t("photo.add"), onClick: () => input.current?.click() }}
        />
        <input
          ref={input}
          type="file"
          accept="image/*"
          hidden
          onChange={(event) => void choose(event.target.files?.[0])}
        />
        {shown && (
          <Button variant="plain" onClick={() => setPhoto({ kind: "none" })}>
            {t("photo.remove")}
          </Button>
        )}

        <ChoiceChips label={t("wish.what")} options={kinds().map(({ value, label }) => ({ value, label }))} value={kind} onChange={setKind} />

        <TextField label={t("wish.name")} value={name} onChange={setName} placeholder={hints.name} autoFocus={!wish} />

        {place && !picking ? (
          <div className="outings-place-chosen">
            <ListRow
              title={place.name}
              subtitle={placeLine(place) === place.name ? undefined : placeLine(place)}
              detail={place.lat == null ? t("place.unplaced") : undefined}
              icon="pin"
              hue={kindOf(kind).hue}
              accessory="edit"
              onClick={() => setPicking(true)}
            />
            <Button variant="plain" onClick={() => setPlace(null)}>
              {t("place.remove")}
            </Button>
          </div>
        ) : (
          <PlacePicker
            placeholder={hints.place}
            onPick={(picked) => {
              setPlace(picked);
              setPicking(false);
            }}
          />
        )}

        <label className="text-field">
          <span className="text-field-label">{t("wish.text")}</span>
          <textarea
            className="text-field-input outings-textarea"
            value={body}
            rows={4}
            placeholder={hints.body}
            onChange={(event) => setBody(event.target.value)}
          />
        </label>

        {problem && <Hint tone="warning">{problem}</Hint>}
      </div>
    </Sheet>
  );
}
