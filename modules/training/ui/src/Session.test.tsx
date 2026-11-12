import { renderToString } from "react-dom/server";

import { DeleteSessionSheet, SessionScreen, TimesSheet, slotAfter } from "./Session";
import { LAST_PRESS, SESSION } from "./fixtures";
import { SyncQueue } from "./queue";

function render(session = SESSION, queue = new SyncQueue({ storage: null })) {
  return renderToString(<SessionScreen id={session.id} initial={session} queue={queue} onExit={() => undefined} />).replaceAll(
    "<!-- -->",
    "",
  );
}

describe("la pantalla de sesión", () => {
  it("todos los ejercicios en una lista; el primero abierto, con la variante y la carga de la última vez", () => {
    const html = render();

    expect(html).toContain('class="surface disclosure-list" aria-label="Ejercicios"');
    expect(html.match(/aria-expanded="true"/g)).toHaveLength(1);
    expect(html.match(/aria-expanded="false"/g)).toHaveLength(1);
    expect(html).toMatch(/role="radio"[^>]*aria-checked="true"[^>]*>Prensa</);
    expect(html).toContain("La última vez, 12 sept: 10, 9 × 140 kg");
    expect(html).toContain(">140<");
    expect(html).toContain(">10<");
    expect(html).toContain('aria-label="Confirmar serie 1"');
  });

  it("cada ejercicio cerrado dice su objetivo y la última vez", () => {
    const html = render();

    expect(html).toContain("2 × 8–12 · primera vez");
  });

  it("si la última vez fue en otro centro, lo dice: allí era otra máquina", () => {
    const elsewhere = { ...LAST_PRESS, gym_id: "g2", gym: "Otro centro" };
    const html = render({ ...SESSION, history: [elsewhere] });

    expect(html).toContain("La última vez, 12 sept en Otro centro: 10, 9 × 140 kg");
  });

  it("con mancuernas se apunta el peso de una", () => {
    const [first, ...rest] = SESSION.slots;
    const dumbbells = { ...first!, options: first!.options.map((option) => ({ ...option, implement: "dumbbell" })) };
    const html = render({ ...SESSION, slots: [dumbbells, ...rest] });

    expect(html).toContain("kg por mancuerna");
    expect(html).toContain('aria-label="Peso por mancuerna"');
  });

  it("la serie que toca, en su fila; las que faltan, con lo propuesto en gris", () => {
    const html = render();

    expect(html).toMatch(/class="sequence-row" data-state="now"><span class="sequence-number">1</);
    expect(html).toMatch(/data-state="todo"><span class="sequence-number">2<\/span><span class="sequence-value">9 × 140 kg/);
    expect(html).toContain('data-size="small"');
  });

  it("lo secundario no estorba: la nota plegada, la superserie a mano y borrar al final", () => {
    const html = render();

    expect(html).toContain(">Añadir nota<");
    expect(html).toContain(">Superserie<");
    expect(html).toContain("Borrar entreno");
  });

  it("una serie que no llegó al servidor se ve pendiente tras recargar", () => {
    const storage = new Map<string, string>();
    const persisted = new SyncQueue({
      storage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => void storage.set(key, value) },
      fetcher: (() => new Promise(() => undefined)) as unknown as typeof fetch,
    });
    persisted.enqueue({
      key: "exercise:e1",
      session: "s1",
      method: "PUT",
      path: "/sessions/s1/exercises/e1",
      body: { variant_id: LAST_PRESS.variant_id, plan_slot_id: "slot-squat" },
    });
    persisted.enqueue({
      key: "set:e1:1",
      session: "s1",
      method: "PUT",
      path: "/sessions/s1/exercises/e1/sets/1",
      body: { reps: 10, weight: 140, added_load: null, completed: true, confirmed_at: "2026-09-15T17:05:00Z" },
    });

    const html = render(SESSION, persisted);

    expect(html).toContain("1 sin enviar");
    expect(html).toContain("Serie 1: 10 × 140 kg");
    expect(html).toContain('aria-label="Confirmar serie 2"');
  });

  it("los planner: descanso grande y sesión", () => {
    const html = render();

    expect(html).toContain("Descanso");
    expect(html).toContain("Sesión");
  });
});

describe("una sesión ya terminada", () => {
  it("enseña lo que duró y su fecha, no planner que siguen contando", () => {
    const html = render({ ...SESSION, ended_at: "2022-03-31T17:30:00Z", duration_seconds: 5400, day: "2022-03-31" });

    expect(html).toContain("Duración");
    expect(html).toContain("1 h 30 min");
    expect(html).not.toContain("Descanso");
    expect(html).toContain("2022");
  });
});

describe("borrar un entreno", () => {
  it("un entreno terminado lo ofrece y la confirmación dice qué se pierde, con cancelar a mano", () => {
    expect(render({ ...SESSION, ended_at: "2026-09-16T07:00:00Z", duration_seconds: 3600 })).toContain("Borrar entreno");
    const html = renderToString(
      <DeleteSessionSheet title="Push · jue, 31 mar 2022" sets={24} onCancel={() => undefined} onDelete={async () => undefined} />,
    ).replaceAll("<!-- -->", "");
    expect(html).toContain("¿Borrar este entreno?");
    expect(html).toContain("Push · jue, 31 mar 2022");
    expect(html).toContain("Se borran sus 24 series y sus notas. No se puede deshacer.");
    expect(html).toMatch(/Cancelar.*Borrar entreno/);
  });
});

describe("un entreno terminado", () => {
  const finished = {
    ...SESSION,
    ended_at: "2026-09-16T07:00:00Z",
    duration_seconds: 14 * 3600,
  };

  it("dice lo que duró y de qué hora a qué hora, y se puede cambiar", () => {
    const html = render(finished);

    expect(html).toContain("14 h 00 min");
    expect(html).toContain('aria-label="Cambiar horas: de 19:00 a 09:00"');
  });

  it("la hoja trae las horas que tiene y la duración que saldría", () => {
    const html = renderToString(
      <TimesSheet
        day={finished.day}
        startedAt={finished.started_at}
        endedAt={finished.ended_at}
        onCancel={() => undefined}
        onSave={async () => undefined}
      />,
    ).replaceAll("<!-- -->", "");

    expect(html).toContain('value="19:00"');
    expect(html).toContain('value="09:00"');
    expect(html).toContain("Duración: 14 h 00 min, terminó al día siguiente");
  });
});

describe("al terminar (T-B05)", () => {
  const set = (number: number, reps: number, weight: number) => ({
    number,
    reps,
    weight,
    added_load: null,
    completed: true,
    confirmed_at: "2026-09-15T17:10:00Z",
  });
  const finished = {
    ...SESSION,
    ended_at: "2026-09-15T18:15:00Z",
    duration_seconds: 75 * 60,
    exercises: [
      {
        id: "e1",
        plan_slot_id: "slot-squat",
        variant_id: "v-smith",
        variant: "Smith",
        position: 1,
        sets: [set(1, 8, 62.5), set(2, 8, 62.5)],
      },
    ],
  };
  const outcome = {
    session_id: "s1",
    muscles: [
      { muscle: "quads", name: "Cuádriceps", sets: 2 },
      { muscle: "glutes", name: "Glúteo", sets: 1 },
    ],
    records: [{ variant_id: "v-smith", range: "6-10", reps: 8, load: 62.5, previous: 60 }],
  };
  const html = renderToString(
    <SessionScreen
      id="s1"
      initial={finished}
      initialOutcome={outcome}
      queue={new SyncQueue({ storage: null })}
      onExit={() => undefined}
    />,
  ).replaceAll("<!-- -->", "");

  it("dice cuánto duró, cuántas series y cuántos récords", () => {
    expect(html).toContain("<dt>minutos</dt><dd>75</dd>");
    expect(html).toContain("<dt>series</dt><dd>2</dd>");
    expect(html).toContain('<div data-lit=""><dt>récord</dt><dd>1</dd>');
  });

  it("pinta lo trabajado sobre el cuerpo", () => {
    expect(html).toContain('aria-label="Lo trabajado, de frente"');
    expect(html).toContain("<title>Cuádriceps: 2 series</title>");
  });

  it("cada ejercicio, contra la vez anterior y con su récord", () => {
    expect(html).toContain('aria-label="Mejor serie contra la última vez: +2,5 kg, récord"');
    expect(html).toContain(">Récord</span>");
  });
});

describe("cambiar de ejercicio (T-B05)", () => {
  const [squat, dips] = SESSION.slots as [(typeof SESSION.slots)[number], (typeof SESSION.slots)[number]];
  const logged = (slot: string, sets: number) => ({
    id: `e-${slot}`,
    plan_slot_id: slot,
    variant_id: "v",
    variant: "",
    position: 1,
    sets: Array.from({ length: sets }, (_, index) => ({
      number: index + 1,
      reps: 8,
      weight: 50,
      added_load: null,
      completed: true,
      confirmed_at: "2026-09-15T17:05:00Z",
    })),
  });

  it("en superserie, cada serie lleva al otro ejercicio mientras le queden", () => {
    const pair = [squat.id, dips.id];
    expect(slotAfter(SESSION, [logged(squat.id, 1)], squat.id, pair)).toBe(dips.id);
    expect(slotAfter(SESSION, [logged(squat.id, 1), logged(dips.id, 1)], dips.id, pair)).toBe(squat.id);
  });

  it("si al otro ya no le quedan, sigue en este hasta cerrarlo", () => {
    const pair = [squat.id, dips.id];
    expect(slotAfter(SESSION, [logged(squat.id, 1), logged(dips.id, dips.target_sets)], squat.id, pair)).toBeNull();
  });

  it("sin superserie, solo al cerrar un ejercicio se pasa al siguiente que falte", () => {
    expect(slotAfter(SESSION, [logged(squat.id, 1)], squat.id, null)).toBeNull();
    expect(slotAfter(SESSION, [logged(squat.id, squat.target_sets)], squat.id, null)).toBe(dips.id);
  });

});
