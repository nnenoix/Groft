import React from "react";
import { Avatar } from "./primitives/Avatar";
import { Icon } from "./icons";

interface ComposerDockProps {
  onOpen: () => void;
}

export function ComposerDock({ onOpen }: ComposerDockProps) {
  function open() {
    onOpen();
    setTimeout(
      () => (document.querySelector("[data-composer-input]") as HTMLElement | null)?.focus(),
      80,
    );
  }

  return (
    <button
      onClick={open}
      className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-[var(--radius-md)] text-left transition-all hover:shadow-sm"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-xs)",
      }}
    >
      <div className="relative shrink-0">
        <Avatar name="opus" letter="O" size={26} />
        <span
          className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full pulse-dot"
          style={
            {
              background: "var(--accent-primary)",
              border: "1.5px solid var(--bg-card)",
              "--accent-glow": "oklch(0.72 0.13 45 / 0.3)",
            } as React.CSSProperties
          }
        />
      </div>
      <div className="min-w-0 flex-1">
        <div
          className="text-[12px] font-semibold leading-tight"
          style={{ color: "var(--text-primary)" }}
        >
          Что поручить opus?
        </div>
        <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
          нажми <kbd className="!text-[9px] !py-0 !px-1">/</kbd> или клик
        </div>
      </div>
      <Icon.ArrowRight size={12} style={{ color: "var(--text-muted)" }} />
    </button>
  );
}
