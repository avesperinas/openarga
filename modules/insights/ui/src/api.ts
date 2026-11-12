import { createApi } from "@openarga/app";

export { Unauthorised, problemOf, signIn } from "@openarga/app";

export const api = createApi("insights");

export const PROFILE = "profile";
export const INSIGHTS = "insights";
const { get, send } = api;

export type Rating = "useful" | "known" | "not_applicable";

export interface Figure {
  label: string;
  value: number;
  unit: string | null;
  baseline: number;
  baseline_label: string;
}

export interface Proposal {
  what: string;
  figure: Figure;
  how: string;
}

export interface Insight {
  id: string;
  kind: "alert" | "weekly";
  domain: "money" | "body" | "time" | "leisure" | "cross";
  topic: string;
  title: string;
  body: string;
  figures: Figure[];
  affects: string;
  action: string;
  created_at: string;
  read_at: string | null;
  rating: Rating | null;
  rated_at: string | null;
  proposals?: Proposal[];
}

export interface Profile {
  name: string;
  about: string;
  named: boolean;
}

export interface Signal {
  id: string;
  kind: "deviation" | "jump" | "trend" | "streak" | "stall" | "goal" | "month_pace" | "cross";
  domain: Insight["domain"];
  text: string;
  label: string;
  unit: string | null;
  value: number;
  baseline: number;
  baseline_label: string;
  day: string;
  since: string | null;
  strength: number;
  keys: string[];
}

export interface LastRun {
  kind: "morning" | "weekly";
  key: string;
  asked_at: string;
  signals: number;
  state: string;
  detail: string | null;
  attempt?: number;
  ran_with?: string | null;
  fix?: string | null;
}

export const readInsights = () => get<Insight[]>("/insights");
export const readSignals = () => get<Signal[]>("/signals");
export const readRuns = () => get<LastRun[]>("/runs");
export const markRead = (id: string) => send<Insight>(`/insights/${id}/read`, "POST");
export const rateInsight = (id: string, rating: Rating | null) =>
  send<Insight>(`/insights/${id}/rating`, "PUT", { rating });
export const readProfile = () => get<Profile>("/profile");
export const saveProfile = (name: string, about: string) => send<Profile>("/profile", "PUT", { name, about });

export const readVersion = api.readVersion;

export interface Message {
  id: string;
  author: "person" | "insights";
  body: string;
  created_at: string;
}

export interface Thread {
  id: string;
  title: string;
  insight_id: string | null;
  waiting_since: string | null;
  problem: string | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadOut extends Thread {
  messages: Message[];
}

export const readThreads = () => get<Thread[]>("/threads");
export const readThread = (id: string) => get<ThreadOut>(`/threads/${id}`);
export const startThread = (text: string, insightId?: string | null) =>
  send<ThreadOut>("/threads", "POST", { text, insight_id: insightId ?? null });
export const say = (id: string, text: string) => send<ThreadOut>(`/threads/${id}/messages`, "POST", { text });
export const askAgain = (id: string) => send<ThreadOut>(`/threads/${id}/retry`, "POST");
export const deleteThread = (id: string) => send<void>(`/threads/${id}`, "DELETE");

export const TODAY = "today";
export const TASTES = "tastes";
export const PICKS = "picks";
export const PILLS = "pills";

export type PillReaction = "interested" | "known" | "other";

export interface PillSection {
  title: string;
  text: string;
}

export interface Pill {
  id: string;
  day: string;
  origin: "daily" | "surprise" | "branch";
  run_key: string | null;
  parent_id: string | null;
  depth: number;
  family_key: string;
  topic: string;
  hook: string | null;
  language: string;
  minutes: number;
  headline: string;
  lead: string;
  sections: PillSection[];
  to_tell: string;
  to_think: string | null;
  branches: { title: string; why: string }[];
  sources: { title: string; url: string; language?: string }[];
  glossary: { word: string; meaning: string }[];
  reaction: PillReaction | null;
  read_at: string | null;
  created_at: string;
  audio?: { duration: number; timeline: number[] } | null;
}

export interface PillLine {
  id: string;
  day: string;
  origin: Pill["origin"];
  family_key: string;
  topic: string;
  headline: string;
  minutes: number;
  reaction: PillReaction | null;
  read_at: string | null;
  parent_id: string | null;
}

export interface Fact {
  id: string;
  day: string;
  family_key: string;
  text: string;
  detail: string | null;
  source: { title?: string; url?: string };
  reaction: "interested" | "known" | null;
  created_at: string;
}

export type PickKind = "book" | "podcast" | "episode" | "film" | "series" | "documentary" | "video" | "article" | "course";
export type PickState = "new" | "saved" | "doing" | "done" | "dismissed";

export interface Recommendation {
  id: string;
  kind: PickKind;
  list: "read" | "watch" | "listen";
  title: string;
  creators: string[];
  year: number | null;
  length: string | null;
  language: string | null;
  why: string;
  because: string[];
  origin: "pill" | "weekly" | "event" | "chat";
  pill_id: string | null;
  verified: "catalog" | "link";
  links: { label: string; url: string }[];
  state: PickState;
  collections: string[];
  rating: number | null;
  more_like: boolean | null;
  note: string | null;
  sent_to: string | null;
  has_cover: boolean;
  created_at: string;
  updated_at: string;
}

export interface Ask {
  id: string;
  kind: "pill" | "more" | "picks" | "profile";
  key: string;
  origin: Pill["origin"] | null;
  parent_id: string | null;
  branch: string | null;
  family_key: string | null;
  asked_at: string;
  state: "waiting" | "ready" | "failed" | "refused";
  detail: string | null;
  pill_id: string | null;
}

export type QuestionKind = "one" | "many" | "scale" | "either" | "confirm" | "free";

export interface Question {
  id: string | null;
  origin: "start" | "pass";
  bank_key: string | null;
  kind: QuestionKind;
  text: string;
  why: string | null;
  options: { value: string; label: string }[];
  topic?: string | null;
  trait_id?: string | null;
  asked_at?: string | null;
  answered_at?: string | null;
}

export interface Answer {
  values?: string[];
  text?: string;
  value?: string;
}

export interface Onboarding {
  done: boolean;
  answered: number;
  total: number;
  questions: Question[];
}

export type Facet = "topic" | "genre" | "format" | "creator" | "work" | "style" | "avoid" | "context" | "language";

export interface Trait {
  id: string;
  facet: Facet;
  label: string;
  stance: number;
  source: "said" | "answered" | "seen" | "rated";
  evidence: string | null;
  status: "proposed" | "confirmed" | "rejected";
  updated_at: string;
}

export type Hue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export interface Family {
  key: string;
  name: string;
  hue: Hue;
  glyph: string;
  themes: string;
  weight: number;
  outside: boolean;
}

export interface Source {
  id: string;
  family_key: string;
  name: string;
  kind: string;
  language: string;
  url: string;
  builtin: boolean;
  hidden: boolean;
}

export interface Settings {
  pill_on: boolean;
  pill_time: string;
  pill_minutes: 5 | 10 | 15 | 20 | 30;
  pill_language: string | null;
  pill_level: string | null;
  questions: "never" | "sometimes" | "daily";
  started_at: string | null;
}

export interface Tastes {
  traits: Trait[];
  families: Family[];
  sources: Source[];
  settings: Settings;
  onboarding: Onboarding;
}

export interface Today {
  day: string;
  pill: Pill | null;
  asked: Ask | null;
  facts: Fact[];
  picks: Recommendation[];
  question: Question | null;
  onboarding: Onboarding;
  settings: Settings;
  streak: number;
  unread: number;
  latest: Insight | null;
  waiting: Ask[];
}

export interface PillOut {
  pill: Pill;
  picks: Recommendation[];
  children: PillLine[];
  parent: PillLine | null;
}

export const readToday = () => get<Today>("/today");
export const readPill = (id: string) => get<PillOut>(`/pills/${id}`);
export const readPills = () => get<PillLine[]>("/pills");
export const markPillRead = (id: string) => send<Pill>(`/pills/${id}/read`, "POST");
export const reactPill = (id: string, reaction: PillReaction | null) =>
  send<Pill>(`/pills/${id}/reaction`, "PUT", { reaction });
export const askMore = (origin: "surprise" | "branch", parentId?: string, branch?: string) =>
  send<Ask>("/pills/more", "POST", { origin, parent_id: parentId ?? null, branch: branch ?? null });
export const readAsk = (id: string) => get<Ask>(`/asks/${id}`);
export const reactFact = (id: string, reaction: Fact["reaction"]) => send<Fact>(`/facts/${id}/reaction`, "PUT", { reaction });

export const readTastes = () => get<Tastes>("/tastes");
export const readOnboarding = () => get<Onboarding>("/onboarding");
export const answerStart = (key: string, answer: Answer | null) =>
  send<Onboarding>(`/onboarding/${key}`, "POST", { answer });
export const answerQuestion = (id: string, answer: Answer | null) =>
  send<Question>(`/questions/${id}/answer`, "POST", { answer });
export const changeTrait = (id: string, change: Partial<Pick<Trait, "status" | "stance" | "label">>) =>
  send<Trait>(`/traits/${id}`, "PUT", change);
export const addTrait = (facet: Facet, label: string, stance: number) => send<Trait>("/traits", "POST", { facet, label, stance });
export const forgetTrait = (id: string) => send<void>(`/traits/${id}`, "DELETE");
export const changeFamily = (key: string, change: Partial<Pick<Family, "weight" | "name" | "themes">>) =>
  send<Family>(`/families/${key}`, "PUT", change);
export const addSource = (body: { family_key: string; name: string; kind: string; language: string; url: string }) =>
  send<Source>("/sources", "POST", body);
export const changeSource = (id: string, hidden: boolean) => send<Source>(`/sources/${id}`, "PUT", { hidden });
export const saveSettings = (change: Partial<Omit<Settings, "started_at">>) => send<Settings>("/settings", "PUT", change);

export const readPicks = () => get<Recommendation[]>("/picks");
export const changePick = (id: string, change: Partial<Pick<Recommendation, "state" | "collections" | "rating" | "more_like" | "note">>) =>
  send<Recommendation>(`/picks/${id}`, "PUT", change);
export const savePick = (id: string) => send<Recommendation>(`/picks/${id}/save`, "POST");
export const audioOf = (pill: Pill) =>
  pill.audio ? { src: `/api/insights/pills/${pill.id}/audio`, duration: pill.audio.duration, timeline: pill.audio.timeline } : null;

export const coverOf = (pick: Recommendation) => (pick.has_cover ? `/api/insights/picks/${pick.id}/cover` : null);
