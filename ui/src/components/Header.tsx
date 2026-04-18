import ConnectionStatus from "./ConnectionStatus";
import type { WSStatus } from "../hooks/useWebSocket";

export interface HeaderProps {
  agentCount: number;
  connectionStatus: WSStatus;
}

function Header({ agentCount, connectionStatus }: HeaderProps) {
  return (
    <header className="h-12 px-4 flex items-center justify-between bg-bg-secondary border-b border-border shrink-0">
      <div className="flex items-center gap-2">
        <span className="w-4 h-4 bg-accent-primary rounded-sm" />
        <span className="text-text-primary font-semibold">ClaudeOrch</span>
      </div>
      <ConnectionStatus status={connectionStatus} />
      <div className="text-text-muted text-sm">{agentCount} агента</div>
    </header>
  );
}

export default Header;
