import { createApi } from "@openarga/app";

const { get, send } = createApi("hub");

export type AiProvider = "none" | "fake" | "anthropic" | "openai";

export interface AiChoice {
  provider: AiProvider | null;
  base_url: string | null;
  fast_model: string | null;
  smart_model: string | null;
  monthly_tokens: number | null;
}

export interface AiSettings {
  provider: AiProvider;
  base_url: string | null;
  fast_model: string | null;
  smart_model: string | null;
  monthly_tokens: number | null;
  key_hint: string | null;
  own_key: boolean;
  instance_key: boolean;
  mine: AiChoice;
  updated_at: string | null;
}

export interface AiAttempt {
  id: string;
  app: string;
  capability: "extract" | "run";
  role: "fast" | "smart";
  provider: string;
  model: string;
  status: "queued" | "running" | "done" | "failed" | "over_budget";
  steps: number;
  input_tokens: number;
  output_tokens: number;
  detail: string | null;
  summary: string | null;
  started_at: string;
}

export interface AiSpending {
  spent: number;
  monthly_tokens: number | null;
  attempts: AiAttempt[];
}

export const readAiSettings = () => get<AiSettings>("/ai/settings");
export const saveAiSettings = (choice: AiChoice) => send<AiSettings>("/ai/settings", "PUT", choice);
export const saveAiKey = (key: string) => send<void>("/ai/key", "PUT", { key });
export const forgetAiKey = () => send<void>("/ai/key", "DELETE");
export const readAiSpending = () => get<AiSpending>("/ai/attempts");
