export const MODEL_OPTIONS = [
  "claude-opus-4-7",
  "claude-sonnet-4-6",
  "claude-haiku-4-5-20251001",
] as const;

export type ModelId = typeof MODEL_OPTIONS[number];

export const DEFAULT_MODEL: ModelId = "claude-opus-4-7";
