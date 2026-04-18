import type React from "react";

interface EmptyStateProps {
  icon: React.ComponentType<{ size?: number }>;
  title: string;
  desc: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: IconComp, title, desc, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full py-[var(--pad-10)] text-center">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center mb-[var(--pad-4)]"
        style={{ background: "var(--accent-light)", color: "var(--accent-hover)" }}
      >
        <IconComp size={28} />
      </div>
      <div className="text-[17px] font-semibold mb-1" style={{ color: "var(--text-primary)" }}>{title}</div>
      <div className="text-[13px] max-w-[360px]" style={{ color: "var(--text-muted)" }}>{desc}</div>
      {action && <div className="mt-[var(--pad-4)]">{action}</div>}
    </div>
  );
}

export default EmptyState;
