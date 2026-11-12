import { prime } from "@openarga/app";
import { Button, Card, ErrorState, Hint, Skeleton, TextAreaField, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { PROFILE, type Profile, Unauthorised, readProfile, saveProfile, signIn } from "./api";
import { NAME } from "./Header";

export function ProfileSettings({ onSaved }: { onSaved: (profile: Profile) => void }) {
  const [name, setName] = useState("");
  const [about, setAbout] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [unread, setUnread] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setUnread(null);
    void readProfile()
      .then((profile) => {
        if (!live) return;
        setName(profile.named ? profile.name : "");
        setAbout(profile.about);
        setLoaded(true);
        prime(PROFILE, profile);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (live) setUnread(error instanceof Error ? error.message : "");
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  if (!loaded && unread !== null)
    return (
      <ErrorState
        title="No se pudo leer tu perfil"
        detail={unread || undefined}
        onRetry={() => setAttempt((n) => n + 1)}
      />
    );
  if (!loaded) return <Skeleton label="Cargando lo que sabe de ti" />;

  const save = () => {
    setState("saving");
    void saveProfile(name, about)
      .then((profile) => {
        setState("saved");
        onSaved(profile);
      })
      .catch(() => setState("failed"));
  };

  return (
    <Card title="Tú y Insights">
      <TextField
        label="Su nombre"
        value={name}
        placeholder={NAME}
        hint="El que quieras. Sin nombre, se llama Insights."
        onChange={(value) => {
          setName(value);
          setState("idle");
        }}
      />
      <TextAreaField
        label="Lo que quieres que sepa de ti"
        value={about}
        rows={8}
        max={8000}
        placeholder="Qué te importa ahora, tus metas, tu contexto y de qué no quieres que te hable."
        onChange={(value) => {
          setAbout(value);
          setState("idle");
        }}
      />
      {state === "failed" && <Hint tone="warning">No se pudo guardar.</Hint>}
      <Button variant="primary" disabled={!loaded || state === "saving"} onClick={save}>
        {state === "saved" ? "Guardado" : "Guardar"}
      </Button>
    </Card>
  );
}
