import { Button, GroupLabel, Hint, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import { type Place, clearHome, setHome } from "./api";
import { PlacePicker } from "./PlacePicker";
import { flag } from "./words";
import { t } from "./lang";

export function HomePlace({ home, onChanged }: { home: Place | null; onChanged: () => void }) {
  const [choosing, setChoosing] = useState(false);
  const [failed, setFailed] = useState("");

  const choose = async (place: Place) => {
    setFailed("");
    try {
      await setHome(place.id);
      setChoosing(false);
      onChanged();
    } catch (error) {
      setFailed(error instanceof Error ? error.message : t("home.error.save"));
    }
  };

  const forget = async () => {
    setFailed("");
    try {
      await clearHome();
      setChoosing(false);
      onChanged();
    } catch (error) {
      setFailed(error instanceof Error ? error.message : t("docs.error.remove"));
    }
  };

  return (
    <section className="travel-group">
      <GroupLabel>
        {t("home.title")}
        <span className="travel-group-detail">{t("home.detail")}</span>
      </GroupLabel>
      {home ? (
        <List>
          <ListRow
            title={`${flag(home.country_code)} ${home.name}`}
            subtitle={[home.region, home.country].filter(Boolean).join(", ") || t("other.unplaced")}
            accessory="chevron-right"
            aria-label={t("home.change", { name: home.name })}
            onClick={() => setChoosing(true)}
          />
        </List>
      ) : (
        <>
          <Hint>
            {t("home.hint")}
          </Hint>
          <Button variant="secondary" icon="plus" onClick={() => setChoosing(true)}>
            {t("home.choose")}
          </Button>
        </>
      )}

      {choosing && (
        <Sheet title={t("home.title")} onClose={() => setChoosing(false)}>
          <div className="travel-sheet-stack">
            <PlacePicker label={t("home.place")} onPick={(place) => void choose(place)} />
            {home && (
              <Button variant="plain" onClick={() => void forget()}>
                {t("home.forget")}
              </Button>
            )}
            {failed && (
              <Hint tone="warning">
                {failed}
              </Hint>
            )}
          </div>
        </Sheet>
      )}
    </section>
  );
}
