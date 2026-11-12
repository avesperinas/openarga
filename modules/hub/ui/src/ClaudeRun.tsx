import { Button, Card, ConfirmDelete, Hint, List, ListRow, Switch } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import {
  type ClaudeRunApp,
  type ConnectionDetail,
  authorizeClaudeRun,
  readClaudeRun,
  revokeClaudeRun,
  setRelay,
} from "./api";

const DAY = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long" });

export function grantLine(app: ClaudeRunApp, connection: string, relay = false): string {
  if (!app.granted) return "Sin permiso.";
  if (app.granted.connection !== connection) {
    const elsewhere = `La usa con tu cuenta «${app.granted.label}»`;
    return relay ? `${elsewhere}; esta la cubre si aquella no puede.` : `${elsewhere}.`;
  }
  return `La usa desde el ${DAY.format(new Date(app.granted.since))}.`;
}

export function ClaudeRun({
  connection,
  relay = true,
  onChange,
}: {
  connection: string;
  relay?: boolean;
  onChange?: (changed: ConnectionDetail) => void;
}) {
  const [state, setState] = useState<{ configured: boolean; apps: ClaudeRunApp[] } | null>(null);
  const [removing, setRemoving] = useState<ClaudeRunApp | null>(null);
  const [problem, setProblem] = useState("");
  const returned = new URLSearchParams(window.location.search).get("claude");

  const load = useCallback(() => {
    readClaudeRun()
      .then(setState)
      .catch(() => setProblem("No se pudo leer qué apps usan tu Claude."));
  }, []);
  useEffect(load, [load]);

  if (state === null && !problem) return null;
  const welcomed = state?.apps.find((app) => app.id === returned);

  return (
    <Card title="Tu Claude en arga">
      <Hint>
        Las apps que lo tienen permitido lanzan esta cuenta solas, con tu suscripción: leen tus datos
        y solo escriben en su propia app.
      </Hint>
      {welcomed && <Hint announce>Listo: {welcomed.name} ya puede usar esta cuenta.</Hint>}
      {state && !state.configured && <Hint tone="warning">arga todavía no puede lanzar tu Claude.</Hint>}
      {state && state.apps.length > 0 && (
        <List>
          {state.apps.map((app) => {
            const here = app.granted?.connection === connection;
            return (
              <ListRow
                key={app.id}
                title={app.name}
                detail={grantLine(app, connection, relay)}
                accessory={here ? undefined : "chevron-right"}
                onClick={
                  here || !state.configured
                    ? () => setRemoving(here ? app : null)
                    : () => window.location.assign(authorizeClaudeRun(connection, app.id))
                }
              />
            );
          })}
        </List>
      )}
      <div className="hub-actions">
        <Switch
          label="Relevo: hacer las pasadas de tus otras cuentas de Claude cuando ellas no puedan"
          checked={relay}
          onChange={(on) =>
            setRelay(connection, on)
              .then((changed) => onChange?.(changed))
              .catch(() => setProblem("No se pudo cambiar el relevo."))
          }
        />
      </div>
      <Hint>
        Con el relevo, si la cuenta con la que una app usa tu Claude está sin hueco o sin token, la pasada la
        hace esta.
      </Hint>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {removing && (
        <ConfirmDelete
          title={`¿Quitar el permiso de ${removing.name}?`}
          subject={removing.name}
          consequence="Deja de poder lanzar tu Claude hasta que se lo vuelvas a dar. Lo que ya apuntó se queda."
          action="Quitar permiso"
          onCancel={() => setRemoving(null)}
          onConfirm={() =>
            revokeClaudeRun(removing.id)
              .then(() => {
                setRemoving(null);
                load();
              })
              .catch(() => setProblem("No se pudo quitar el permiso."))
          }
        />
      )}
      {state && state.apps.some((app) => !app.granted) && state.configured && (
        <div className="hub-actions">
          <Button variant="plain" onClick={load}>
            Actualizar
          </Button>
        </div>
      )}
    </Card>
  );
}
