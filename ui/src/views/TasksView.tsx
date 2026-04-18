import { useMemo } from "react";
import type { Tasks, Task } from "../store/agentStore";
import { TaskCard, EyebrowLabel } from "../components/primitives";
import { Icon } from "../components/icons";

/* ---------- DepGraph ---------- */
const NODE_W = 84, NODE_H = 22, PAD = 10, COL_W = 110, ROW_H = 36;

function DepGraph({ tasks }: { tasks: Tasks }) {
  const all = useMemo(
    () => [
      ...tasks.current,
      ...tasks.backlog.slice(0, 4),
      ...tasks.done.slice(0, 2),
    ],
    [tasks],
  );

  const idSet = new Set(all.map((t) => t.id));

  const inDeg = useMemo(() => {
    const m = new Map<string, number>(all.map((t) => [t.id, 0]));
    all.forEach((t) => {
      (t.deps ?? []).forEach((d) => {
        if (idSet.has(d)) m.set(t.id, (m.get(t.id) ?? 0) + 1);
      });
    });
    return m;
  }, [all]);

  const colOf = useMemo(() => {
    const map = new Map<string, number>();
    const queue: { id: string; col: number }[] = [];
    all.forEach((t) => {
      if ((inDeg.get(t.id) ?? 0) === 0) queue.push({ id: t.id, col: 0 });
    });
    while (queue.length > 0) {
      const item = queue.shift()!;
      if (map.has(item.id)) continue;
      map.set(item.id, item.col);
      all.forEach((t) => {
        if ((t.deps ?? []).includes(item.id) && idSet.has(t.id) && !map.has(t.id)) {
          queue.push({ id: t.id, col: item.col + 1 });
        }
      });
    }
    all.forEach((t) => { if (!map.has(t.id)) map.set(t.id, 0); });
    return map;
  }, [all, inDeg]);

  const { positions, maxCol, maxRows } = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    const colCount = new Map<number, number>();
    all.forEach((t) => {
      const col = colOf.get(t.id) ?? 0;
      const row = colCount.get(col) ?? 0;
      colCount.set(col, row + 1);
      positions.set(t.id, { x: PAD + col * COL_W, y: PAD + row * ROW_H });
    });
    const maxCol = Math.max(0, ...Array.from(colOf.values()));
    const maxRows = Math.max(1, ...Array.from(colCount.values()));
    return { positions, maxCol, maxRows };
  }, [all, colOf]);

  const edges = useMemo<[string, string][]>(() => {
    const result: [string, string][] = [];
    all.forEach((t) => {
      (t.deps ?? []).forEach((d) => {
        if (idSet.has(d)) result.push([d, t.id]);
      });
    });
    return result;
  }, [all]);

  const vbW = Math.max(310, PAD * 2 + (maxCol + 1) * COL_W);
  const vbH = Math.max(240, PAD * 2 + maxRows * ROW_H + NODE_H);

  return (
    <svg viewBox={`0 0 ${vbW} ${vbH}`} className="w-full h-full" preserveAspectRatio="xMidYMid meet">
      {edges.map(([a, b], i) => {
        const pa = positions.get(a);
        const pb = positions.get(b);
        if (!pa || !pb) return null;
        const mx = (pa.x + NODE_W + pb.x) / 2;
        return (
          <path
            key={i}
            d={`M${pa.x + NODE_W},${pa.y + NODE_H / 2} C${mx},${pa.y + NODE_H / 2} ${mx},${pb.y + NODE_H / 2} ${pb.x},${pb.y + NODE_H / 2}`}
            stroke="var(--border)" strokeWidth="1" fill="none" strokeDasharray="2 3"
          />
        );
      })}
      {all.map((t: Task) => {
        const p = positions.get(t.id);
        if (!p) return null;
        const isActive = t.status === "active";
        const isDone = t.status === "done";
        return (
          <g key={t.id} transform={`translate(${p.x}, ${p.y})`}>
            <rect
              width={NODE_W} height={NODE_H} rx="5"
              fill={isDone ? "var(--bg-secondary)" : isActive ? "var(--accent-light)" : "var(--bg-card)"}
              stroke={isActive ? "var(--accent-primary)" : "var(--border)"} strokeWidth="1"
            />
            <text x="6" y="14" fontSize="9" fontFamily="var(--font-mono)" fill={isActive ? "var(--accent-hover)" : "var(--text-muted)"}>
              {t.id}
            </text>
            <circle
              cx={NODE_W - 8} cy={NODE_H / 2} r="2.5"
              fill={isDone ? "var(--status-active)" : isActive ? "var(--accent-primary)" : "var(--text-dim)"}
            />
          </g>
        );
      })}
    </svg>
  );
}

/* ---------- TasksView ---------- */
interface TasksViewProps {
  tasks: Tasks;
}

const COLUMNS: Array<{ key: keyof Tasks; label: string }> = [
  { key: "backlog", label: "Backlog" },
  { key: "current", label: "In Flight" },
  { key: "done",    label: "Done" },
];

export function TasksView({ tasks }: TasksViewProps) {
  return (
    <div className="h-full overflow-hidden flex flex-col p-[var(--pad-6)]">
      <div className="mb-[var(--pad-5)] flex items-end justify-between shrink-0">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>Pipeline</div>
          <h1 className="text-[28px] font-display font-semibold tracking-tight">Задачи</h1>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn btn-outline text-[12px]"><Icon.GitBranch size={13} /> Граф</button>
          <button className="btn btn-primary text-[12px]"><Icon.Plus size={13} /> Задача</button>
        </div>
      </div>
      <div className="flex-1 min-h-0 grid grid-cols-[1fr_1fr_1fr_280px] gap-[var(--pad-4)]">
        {COLUMNS.map((col) => (
          <div key={col.key} className="flex flex-col min-h-0">
            <div className="mb-[var(--pad-3)]">
              <EyebrowLabel count={tasks[col.key].length}>{col.label}</EyebrowLabel>
            </div>
            <div className="flex-1 overflow-y-auto space-y-[var(--pad-2)] pr-1">
              {tasks[col.key].map((t) => <TaskCard key={t.id} task={t} />)}
            </div>
          </div>
        ))}
        <div className="card p-[var(--pad-4)] flex flex-col min-h-0">
          <EyebrowLabel>Dependencies</EyebrowLabel>
          <div className="flex-1 mt-[var(--pad-3)] overflow-hidden">
            <DepGraph tasks={tasks} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default TasksView;
