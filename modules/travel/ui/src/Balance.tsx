import { Button, CANNOT_UNDO, ConfirmDelete, GroupLabel, Hint, IconButton } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Balance, type Traveller, Unauthorised, addSettlement, readBalance, removeSettlement, signIn } from "./api";
import { type Members, travellerLabel } from "./people";
import { eurosExact } from "./words";

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
      setProblem(error instanceof Error ? error.message : "No se ha podido apuntar.");
    }
  };

  const anyPaid = found?.people.some((one) => one.paid_eur > 0);
  if (!found || (!anyPaid && found.settlements.length === 0)) return null;

  return (
    <section className="travel-group">
      <GroupLabel>Cuentas</GroupLabel>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <div className="surface travel-balance">
        <ol className="travel-balance-people">
          {found.people.map((one) => (
            <li key={one.traveller.id} data-tone={one.net_eur > 0.004 ? "owed" : one.net_eur < -0.004 ? "owes" : "even"}>
              <span className="travel-balance-name">{who(one.traveller)}</span>
              <span className="travel-balance-detail">
                pagó {eurosExact(one.paid_eur)} · le tocaba {eurosExact(one.share_eur)}
              </span>
              <strong className="travel-balance-net">
                {Math.abs(one.net_eur) < 0.005
                  ? "en paz"
                  : one.net_eur > 0
                    ? `le deben ${eurosExact(one.net_eur)}`
                    : `debe ${eurosExact(-one.net_eur)}`}
              </strong>
            </li>
          ))}
        </ol>
        {found.transfers.length > 0 && (
          <ol className="travel-balance-transfers" aria-label="Para quedar en paz">
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
                  Hecho
                </Button>
              </li>
            ))}
          </ol>
        )}
        {found.transfers.length === 0 && <p className="travel-balance-even">Todos en paz.</p>}
        {found.settlements.length > 0 && (
          <ol className="travel-balance-settled" aria-label="Ya devuelto">
            {found.settlements.map((one) => (
              <li key={one.id}>
                <span>
                  {who(one.from_traveller)} devolvió {eurosExact(one.amount_eur)} a {who(one.to_traveller)} ·{" "}
                  {one.settled_on}
                </span>
                <IconButton icon="undo" label="Deshacer la devolución" variant="plain" size="small" onClick={() => setUndoing(one)} />
              </li>
            ))}
          </ol>
        )}
        {found.unassigned_eur > 0 && (
          <p className="travel-balance-even">
            {eurosExact(found.unassigned_eur)} apuntados sin quién pagó no cuentan aquí.
          </p>
        )}
      </div>
      {undoing && (
        <ConfirmDelete
          title="¿Deshacer la devolución?"
          subject={`${who(undoing.from_traveller)} → ${who(undoing.to_traveller)}, ${eurosExact(undoing.amount_eur)}`}
          consequence={`Vuelve a deberse. ${CANNOT_UNDO}`}
          action="Deshacer"
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
