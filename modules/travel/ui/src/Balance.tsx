import { Button, ConfirmDelete, GroupLabel, Hint, IconButton, cannotUndo } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Balance, type Traveller, Unauthorised, addSettlement, readBalance, removeSettlement, signIn } from "./api";
import { type Members, travellerLabel } from "./people";
import { eurosExact } from "./words";
import { t } from "./lang";

export function BalanceSection({ tripId, version, members }: { tripId: string; version: string; members: Members }) {
  const who = (one: Traveller) => travellerLabel(one, members);
  const [found, setFound] = useState<Balance | null>(null);
  const [problem, setProblem] = useState("");
  const [undoing, setUndoing] = useState<Balance["settlements"][number] | null>(null);

  useEffect(() => {
    readBalance(tripId)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setFound(null);
      });
  }, [tripId, version]);

  const apply = async (change: Promise<Balance>) => {
    try {
      setFound(await change);
      setProblem("");
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("today.error.note"));
    }
  };

  const anyPaid = found?.people.some((one) => one.paid_eur > 0);
  if (!found || (!anyPaid && found.settlements.length === 0)) return null;

  return (
    <section className="travel-group">
      <GroupLabel>{t("balance.title")}</GroupLabel>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <div className="surface travel-balance">
        <ol className="travel-balance-people">
          {found.people.map((one) => (
            <li key={one.traveller.id} data-tone={one.net_eur > 0.004 ? "owed" : one.net_eur < -0.004 ? "owes" : "even"}>
              <span className="travel-balance-name">{who(one.traveller)}</span>
              <span className="travel-balance-detail">
                {t("balance.paid_share", { paid: eurosExact(one.paid_eur), share: eurosExact(one.share_eur) })}
              </span>
              <strong className="travel-balance-net">
                {Math.abs(one.net_eur) < 0.005
                  ? t("balance.even")
                  : one.net_eur > 0
                    ? t("balance.owed", { amount: eurosExact(one.net_eur) })
                    : t("balance.owes", { amount: eurosExact(-one.net_eur) })}
              </strong>
            </li>
          ))}
        </ol>
        {found.transfers.length > 0 && (
          <ol className="travel-balance-transfers" aria-label={t("balance.to_settle")}>
            {found.transfers.map((one) => (
              <li key={`${one.from_traveller.id}-${one.to_traveller.id}`}>
                <span>
                  {who(one.from_traveller)} → {who(one.to_traveller)} · <strong>{eurosExact(one.amount_eur)}</strong>
                </span>
                <Button
                  variant="tinted"
                  size="small"
                  onClick={() =>
                    void apply(
                      addSettlement(tripId, {
                        from_traveller: one.from_traveller.id,
                        to_traveller: one.to_traveller.id,
                        amount_eur: one.amount_eur.toFixed(2),
                      }),
                    )
                  }
                >
                  {t("action.done")}
                </Button>
              </li>
            ))}
          </ol>
        )}
        {found.transfers.length === 0 && <p className="travel-balance-even">{t("balance.all_even")}</p>}
        {found.settlements.length > 0 && (
          <ol className="travel-balance-settled" aria-label={t("balance.settled")}>
            {found.settlements.map((one) => (
              <li key={one.id}>
                <span>
                  {t("balance.paid_back", {
                    from: who(one.from_traveller),
                    amount: eurosExact(one.amount_eur),
                    to: who(one.to_traveller),
                  })}{" "}
                  · {one.settled_on}
                </span>
                <IconButton icon="undo" label={t("balance.undo")} variant="plain" size="small" onClick={() => setUndoing(one)} />
              </li>
            ))}
          </ol>
        )}
        {found.unassigned_eur > 0 && (
          <p className="travel-balance-even">
            {t("balance.unassigned", { amount: eurosExact(found.unassigned_eur) })}
          </p>
        )}
      </div>
      {undoing && (
        <ConfirmDelete
          title={t("balance.undo_confirm")}
          subject={`${who(undoing.from_traveller)} → ${who(undoing.to_traveller)}, ${eurosExact(undoing.amount_eur)}`}
          consequence={`${t("balance.undo_consequence")} ${cannotUndo()}`}
          action={t("action.undo")}
          onCancel={() => setUndoing(null)}
          onConfirm={async () => {
            await apply(removeSettlement(tripId, undoing.id));
            setUndoing(null);
          }}
        />
      )}
    </section>
  );
}
