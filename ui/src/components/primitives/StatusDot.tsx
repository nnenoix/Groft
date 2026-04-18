import React from "react";

export type Status =
  | "active"
  | "idle"
  | "stuck"
  | "restarting"
  | "connected"
  | "not-connected"
  | "error"
  | "connecting";

export const STATUS_COLOR: Record<Status, string> = {
  active: "var(--status-active)",
  idle: "var(--status-idle)",
  stuck: "var(--status-stuck)",
  restarting: "var(--status-restarting)",
  connected: "var(--status-active)",
  "not-connected": "var(--status-idle)",
  error: "var(--status-stuck)",
  connecting: "var(--status-restarting)",
};

interface StatusDotProps {
  status: Status;
  size?: number;
  pulse?: boolean;
}

export function StatusDot({ status, size = 8, pulse = false }: StatusDotProps) {
  const color = STATUS_COLOR[status] ?? "var(--text-dim)";
  const doesPulse = pulse && (status === "active" || status === "connected");
  return (
    <span
      className={`inline-block rounded-full${doesPulse ? " pulse-dot" : ""}`}
      style={{ width: size, height: size, backgroundColor: color, "--accent-glow": `${color}33` } as React.CSSProperties}
    />
  );
}

interface StatusLabelProps {
  status: Status;
}

const STATUS_LABEL: Record<Status, string> = {
  active: "Active",
  idle: "Idle",
  stuck: "Stuck",
  restarting: "Restarting",
  connected: "Connected",
  "not-connected": "Not connected",
  error: "Error",
  connecting: "Connecting",
};

export function StatusLabel({ status }: StatusLabelProps) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" style={{ color: STATUS_COLOR[status] }}>
      <StatusDot status={status} pulse />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
