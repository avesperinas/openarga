import type { LastTime, Session, Slot } from "./api";

export const SQUAT: Slot = {
  id: "slot-squat",
  position: 1,
  exercise: "Squat",
  target_sets: 3,
  rep_min: 6,
  rep_max: 10,
  allow_both: false,
  options: [
    { variant_id: "v-smith", name: "Smith machine squat", implement: "smith", min_increment: 2.5, priority: 1 },
    { variant_id: "v-press", name: "Leg press", implement: "machine", min_increment: 5, priority: 2 },
  ],
};

export const DIPS: Slot = {
  id: "slot-dips",
  position: 2,
  exercise: "Dips",
  target_sets: 2,
  rep_min: 8,
  rep_max: 12,
  allow_both: false,
  options: [
    { variant_id: "v-dips", name: "Weighted dips", implement: "bodyweight", min_increment: 2.5, priority: 1 },
  ],
};

export const LAST_PRESS: LastTime = {
  variant_id: "v-press",
  day: "2026-09-12",
  sets: [
    { number: 1, reps: 10, weight: 140, added_load: null, completed: true, confirmed_at: "2026-09-12T17:00:00Z" },
    { number: 2, reps: 9, weight: 140, added_load: null, completed: true, confirmed_at: "2026-09-12T17:03:00Z" },
  ],
};

export const LAST_SMITH: LastTime = {
  variant_id: "v-smith",
  day: "2026-09-08",
  sets: [
    { number: 1, reps: 8, weight: 60, added_load: null, completed: true, confirmed_at: "2026-09-08T17:00:00Z" },
    { number: 2, reps: 8, weight: 60, added_load: null, completed: true, confirmed_at: "2026-09-08T17:03:00Z" },
    { number: 3, reps: 7, weight: 60, added_load: null, completed: true, confirmed_at: "2026-09-08T17:06:00Z" },
  ],
};

export const SESSION: Session = {
  id: "s1",
  rotation_number: 3,
  plan_day_id: "d-leg",
  day_name: "Leg",
  kind: "leg",
  day: "2026-09-15",
  started_at: "2026-09-15T17:00:00Z",
  ended_at: null,
  duration_seconds: null,
  gym_id: "g1",
  slots: [SQUAT, DIPS],
  exercises: [],
  history: [LAST_SMITH, LAST_PRESS],
};
