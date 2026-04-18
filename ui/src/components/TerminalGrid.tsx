import type { AgentStatus } from "./AgentCard";

export interface TerminalData {
  agent: string;
  status: AgentStatus;
  lines: string[];
}

export interface TerminalGridProps {
  terminals: TerminalData[];
}

const STATUS_DOT_COLOR: Record<AgentStatus, string> = {
  active: "#2d7a4f",
  idle: "#999999",
  stuck: "#c0392b",
  restarting: "#d97757",
};

const TIMESTAMP_RE = /^(\d{2}:\d{2})\s(.*)$/;
const CODE_PREFIX_RE = /^(npm |git |python )/;

interface ParsedLine {
  timestamp: string | null;
  body: string;
  isCode: boolean;
}

function parseLine(raw: string): ParsedLine {
  const match = TIMESTAMP_RE.exec(raw);
  if (!match) {
    return { timestamp: null, body: raw, isCode: CODE_PREFIX_RE.test(raw) };
  }
  const [, timestamp, rest] = match;
  return {
    timestamp,
    body: rest,
    isCode: CODE_PREFIX_RE.test(rest),
  };
}

function TerminalCard({ data }: { data: TerminalData }) {
  return (
    <div className="bg-bg-terminal border border-border rounded-lg flex flex-col overflow-hidden shadow-sm min-h-0">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 shrink-0">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: STATUS_DOT_COLOR[data.status] }}
        />
        <span className="font-medium text-sm text-text-primary">
          {data.agent}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-text-terminal space-y-0.5 leading-relaxed">
        {data.lines.map((line, idx) => {
          const parsed = parseLine(line);
          return (
            <div key={idx} className="flex gap-2 whitespace-pre-wrap">
              {parsed.timestamp && (
                <span className="text-text-muted shrink-0">
                  {parsed.timestamp}
                </span>
              )}
              <span
                className={
                  parsed.isCode ? "text-text-code" : "text-text-terminal"
                }
              >
                {parsed.body}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TerminalGrid({ terminals }: TerminalGridProps) {
  return (
    <div className="grid grid-cols-2 grid-rows-2 gap-4 p-6 h-full overflow-hidden">
      {terminals.map((terminal) => (
        <TerminalCard key={terminal.agent} data={terminal} />
      ))}
    </div>
  );
}

export default TerminalGrid;
