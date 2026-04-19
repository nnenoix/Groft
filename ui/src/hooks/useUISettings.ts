import type { UISettings } from "../views/SettingsView";

export const LOCALSTORAGE_KEY = "groft:uiSettings";

export const DEFAULT_UI_SETTINGS: UISettings = {
  theme: "light",
  font: "inter",
  density: "spacious",
  accent: "default",
  backdrop: "froggly",
};

function isTheme(v: unknown): v is UISettings["theme"] {
  return v === "light" || v === "dark";
}

function isFont(v: unknown): v is UISettings["font"] {
  return v === "inter" || v === "geist" || v === "plex";
}

function isDensity(v: unknown): v is UISettings["density"] {
  return v === "compact" || v === "normal" || v === "spacious";
}

function isAccent(v: unknown): v is UISettings["accent"] {
  return v === "default" || v === "violet" || v === "moss" || v === "ocean";
}

function isBackdrop(v: unknown): v is UISettings["backdrop"] {
  return v === "none" || v === "froggly";
}

export function loadUISettings(): UISettings {
  if (typeof localStorage === "undefined") return { ...DEFAULT_UI_SETTINGS };
  let raw: string | null;
  try {
    raw = localStorage.getItem(LOCALSTORAGE_KEY);
  } catch {
    return { ...DEFAULT_UI_SETTINGS };
  }
  if (raw === null) return { ...DEFAULT_UI_SETTINGS };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...DEFAULT_UI_SETTINGS };
  }
  if (parsed === null || typeof parsed !== "object") {
    return { ...DEFAULT_UI_SETTINGS };
  }

  const obj = parsed as Record<string, unknown>;
  const merged: UISettings = { ...DEFAULT_UI_SETTINGS };
  if (isTheme(obj.theme)) merged.theme = obj.theme;
  if (isFont(obj.font)) merged.font = obj.font;
  if (isDensity(obj.density)) merged.density = obj.density;
  if (isAccent(obj.accent)) merged.accent = obj.accent;
  if (isBackdrop(obj.backdrop)) merged.backdrop = obj.backdrop;
  if (typeof obj.projectDir === "string" && obj.projectDir.length > 0) {
    merged.projectDir = obj.projectDir;
  }
  return merged;
}

export function saveUISettings(s: UISettings): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(LOCALSTORAGE_KEY, JSON.stringify(s));
  } catch (err) {
    if (
      err instanceof DOMException &&
      (err.name === "QuotaExceededError" ||
        err.name === "NS_ERROR_DOM_QUOTA_REACHED")
    ) {
      return;
    }
    throw err;
  }
}
