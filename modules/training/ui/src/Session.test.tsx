import { renderToString } from "react-dom/server";

import { DeleteSessionSheet, SessionScreen, TimesSheet, slotAfter } from "./Session";
import { LAST_PRESS, SESSION } from "./fixtures";
import { inLocale } from "./i18n/testing";
import { SyncQueue } from "./queue";

function render(session = SESSION, queue = new SyncQueue({ storage: null })) {
  return renderToString(
    inLocale(<SessionScreen id={session.id} initial={session} queue={queue} onExit={() => undefined} />),
  ).replaceAll(
    "<!-- -->",
    "",
  );
}

describe("the session screen", () => {
  it("all exercises in one list; the first open, with the variant and the load of last time", () => {
    const html = render();

    expect(html).toContain('class="surface disclosure-list" aria-label="Exercises"');
    expect(html.match(/aria-expanded="true"/g)).toHaveLength(1);
    expect(html.match(/aria-expanded="false"/g)).toHaveLength(1);
    expect(html).toMatch(/role="radio"[^>]*aria-checked="true"[^>]*>Leg press</);
    expect(html).toContain("Last time, Sep 12: 10, 9 × 140 kg");
    expect(html).toContain(">140<");
    expect(html).toContain(">10<");
    expect(html).toContain('aria-label="Confirm set 1"');
  });

  it("each closed exercise says its target and the last time", () => {
    const html = render();

    expect(html).toContain("2 × 8–12 · first time");
  });

  it("if last time was at another gym, it says so: it was another machine there", () => {
    const elsewhere = { ...LAST_PRESS, gym_id: "g2", gym: "Other gym" };
    const html = render({ ...SESSION, history: [elsewhere] });

    expect(html).toContain("Last time, Sep 12 at Other gym: 10, 9 × 140 kg");
  });

  it("with dumbbells the weight of one is logged", () => {
    const [first, ...rest] = SESSION.slots;
    const dumbbells = { ...first!, options: first!.options.map((option) => ({ ...option, implement: "dumbbell" })) };
    const html = render({ ...SESSION, slots: [dumbbells, ...rest] });

    expect(html).toContain("kg per dumbbell");
    expect(html).toContain('aria-label="Weight per dumbbell"');
  });

  it("the set due, in its row; the missing ones, with the proposal in grey", () => {
    const html = render();

    expect(html).toMatch(/class="sequence-row" data-state="now"><span class="sequence-number">1</);
    expect(html).toMatch(/data-state="todo"><span class="sequence-number">2<\/span><span class="sequence-value">9 × 140 kg/);
    expect(html).toContain('data-size="small"');
  });

  it("secondary things stay out of the way: the note folded, the superset at hand and delete at the end", () => {
    const html = render();

    expect(html).toContain(">Add note<");
    expect(html).toContain(">Superset<");
    expect(html).toContain("Delete workout");
  });

  it("a set that did not reach the server shows pending after reloading", () => {
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

    expect(html).toContain("1 not sent");
    expect(html).toContain("Set 1: 10 × 140 kg");
    expect(html).toContain('aria-label="Confirm set 2"');
  });

  it("the timers: rest, large, and session", () => {
    const html = render();

    expect(html).toContain("Rest");
    expect(html).toContain("Session");
  });
});

describe("a session already finished", () => {
  it("shows how long it took and its date, not timers that keep counting", () => {
    const html = render({ ...SESSION, ended_at: "2022-03-31T17:30:00Z", duration_seconds: 5400, day: "2022-03-31" });

    expect(html).toContain("Duration");
    expect(html).toContain("1 h 30 min");
    expect(html).not.toContain("Rest");
    expect(html).toContain("2022");
  });
});

describe("deleting a workout", () => {
  it("a finished workout offers it and the confirmation says what is lost, with cancel at hand", () => {
    expect(render({ ...SESSION, ended_at: "2026-09-16T07:00:00Z", duration_seconds: 3600 })).toContain("Delete workout");
    const html = renderToString(
      inLocale(
        <DeleteSessionSheet title="Push · Thu, Mar 31, 2022" sets={24} onCancel={() => undefined} onDelete={async () => undefined} />,
      ),
    ).replaceAll("<!-- -->", "");
    expect(html).toContain("Delete this workout?");
    expect(html).toContain("Push · Thu, Mar 31, 2022");
    expect(html).toContain("Its 24 sets and its notes are deleted. It cannot be undone.");
    expect(html).toMatch(/Cancel.*Delete workout/);
  });
});

describe("a finished workout", () => {
  const finished = {
    ...SESSION,
    ended_at: "2026-09-16T07:00:00Z",
    duration_seconds: 14 * 3600,
  };

  it("says how long it took and from what time to what time, in the zone of the person, and it can change", () => {
    const html = render(finished);

    expect(html).toContain("14 h 00 min");
    expect(html).toContain('aria-label="Change times: from 17:00 to 07:00"');
  });

  it("the sheet brings its times and the duration it would come to", () => {
    const html = renderToString(
      inLocale(
        <TimesSheet
        day={finished.day}
        startedAt={finished.started_at}
        endedAt={finished.ended_at}
        onCancel={() => undefined}
        onSave={async () => undefined}
        />,
      ),
    ).replaceAll("<!-- -->", "");

    expect(html).toContain('value="17:00"');
    expect(html).toContain('value="07:00"');
    expect(html).toContain("Duration: 14 h 00 min, ended the next day");
  });
});

describe("when finishing (T-B05)", () => {
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
      { muscle: "quads", name: "Quads", sets: 2 },
      { muscle: "glutes", name: "Glutes", sets: 1 },
    ],
    records: [{ variant_id: "v-smith", range: "6-10", reps: 8, load: 62.5, previous: 60 }],
  };
  const html = renderToString(
    inLocale(
      <SessionScreen
        id="s1"
        initial={finished}
        initialOutcome={outcome}
        queue={new SyncQueue({ storage: null })}
        onExit={() => undefined}
      />,
    ),
  ).replaceAll("<!-- -->", "");

  it("says how long it took, how many sets and how many records", () => {
    expect(html).toContain("<dt>minutes</dt><dd>75</dd>");
    expect(html).toContain("<dt>sets</dt><dd>2</dd>");
    expect(html).toContain('<div data-lit=""><dt>record</dt><dd>1</dd>');
  });

  it("paints what was worked on the body", () => {
    expect(html).toContain('aria-label="What was worked, ');
    expect(html).toContain("<title>Quads: 2 sets</title>");
  });

  it("each exercise, against the previous time and with its record", () => {
    expect(html).toContain('aria-label="Best set against last time: +2.5 kg, record"');
    expect(html).toContain(">Record</span>");
  });
});

describe("switching exercise (T-B05)", () => {
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

  it("in a superset, each set leads to the other exercise while it has sets left", () => {
    const pair = [squat.id, dips.id];
    expect(slotAfter(SESSION, [logged(squat.id, 1)], squat.id, pair)).toBe(dips.id);
    expect(slotAfter(SESSION, [logged(squat.id, 1), logged(dips.id, 1)], dips.id, pair)).toBe(squat.id);
  });

  it("if the other has none left, it stays on this one until it is closed", () => {
    const pair = [squat.id, dips.id];
    expect(slotAfter(SESSION, [logged(squat.id, 1), logged(dips.id, dips.target_sets)], squat.id, pair)).toBeNull();
  });

  it("without a superset, only closing an exercise moves to the next missing one", () => {
    expect(slotAfter(SESSION, [logged(squat.id, 1)], squat.id, null)).toBeNull();
    expect(slotAfter(SESSION, [logged(squat.id, squat.target_sets)], squat.id, null)).toBe(dips.id);
  });

});
