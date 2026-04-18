type Level = "debug" | "info" | "warn" | "error";

const LEVELS: Record<Level, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

function resolveMinLevel(): number {
  const raw = (import.meta.env.VITE_LOG_LEVEL as string | undefined) ?? "info";
  const key = raw.toLowerCase() as Level;
  return LEVELS[key] ?? LEVELS.info;
}

const MIN = resolveMinLevel();

function stringifyError(err: unknown): string {
  if (err instanceof Error) {
    return err.stack ?? `${err.name}: ${err.message}`;
  }
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

function emit(
  level: Level,
  scope: string,
  msg: string,
  args: unknown[],
): void {
  if (LEVELS[level] < MIN) return;
  const prefix = `[${scope}]`;
  const fn =
    level === "error"
      ? console.error
      : level === "warn"
        ? console.warn
        : level === "debug"
          ? console.debug
          : console.log;
  if (args.length === 0) {
    fn(prefix, msg);
  } else {
    fn(prefix, msg, ...args);
  }
}

export interface Logger {
  debug: (msg: string, ...args: unknown[]) => void;
  info: (msg: string, ...args: unknown[]) => void;
  warn: (msg: string, ...args: unknown[]) => void;
  error: (msg: string, ...args: unknown[]) => void;
  exception: (err: unknown, msg: string, ...args: unknown[]) => void;
}

export function createLogger(scope: string): Logger {
  return {
    debug: (msg, ...args) => emit("debug", scope, msg, args),
    info: (msg, ...args) => emit("info", scope, msg, args),
    warn: (msg, ...args) => emit("warn", scope, msg, args),
    error: (msg, ...args) => emit("error", scope, msg, args),
    exception: (err, msg, ...args) =>
      emit("error", scope, msg, [...args, stringifyError(err)]),
  };
}
