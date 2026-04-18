import type { WSStatus } from "../hooks/useWebSocket";

export interface ConnectionStatusProps {
  status: WSStatus;
}

interface Descriptor {
  label: string;
  dotClass: string;
  textClass: string;
}

const DESCRIPTORS: Record<WSStatus, Descriptor> = {
  connected: {
    label: "Connected",
    dotClass: "text-status-active",
    textClass: "text-status-active",
  },
  connecting: {
    label: "Connecting...",
    dotClass: "text-accent-primary",
    textClass: "text-accent-primary",
  },
  reconnecting: {
    label: "Reconnecting...",
    dotClass: "text-accent-primary",
    textClass: "text-accent-primary",
  },
  disconnected: {
    label: "Offline",
    dotClass: "text-status-stuck",
    textClass: "text-status-stuck",
  },
};

function ConnectionStatus({ status }: ConnectionStatusProps) {
  const d = DESCRIPTORS[status];
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={d.dotClass}>●</span>
      <span className={d.textClass}>{d.label}</span>
    </div>
  );
}

export default ConnectionStatus;
