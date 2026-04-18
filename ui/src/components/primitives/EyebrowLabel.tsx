import React from "react";

interface EyebrowLabelProps {
  children: React.ReactNode;
  count?: number;
  className?: string;
}

export function EyebrowLabel({ children, count, className = "" }: EyebrowLabelProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-[10.5px] uppercase tracking-[0.16em] font-semibold" style={{ color: "var(--text-muted)" }}>
        {children}
      </span>
      {count !== undefined && (
        <span className="text-[10.5px] font-mono" style={{ color: "var(--text-dim)" }}>
          {String(count).padStart(2, "0")}
        </span>
      )}
      <div className="flex-1 hr-soft" />
    </div>
  );
}
