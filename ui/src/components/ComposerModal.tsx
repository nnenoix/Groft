import { useState, useEffect } from "react";
import Composer from "./Composer";
import { Avatar } from "./primitives/Avatar";
import { Icon } from "./icons";

interface ComposerModalProps {
  onClose: () => void;
}

export function ComposerModal({ onClose }: ComposerModalProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div
      className="fixed inset-0 z-40 cmdk-backdrop flex items-start justify-center pt-[14vh] px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-[680px] max-w-[94vw]"
        style={{
          opacity: mounted ? 1 : 0,
          transform: mounted ? "translateY(0) scale(1)" : "translateY(8px) scale(0.98)",
          transition: "opacity 220ms ease-out, transform 280ms cubic-bezier(0.2, 0.9, 0.3, 1)",
        }}
      >
        <div className="mb-3 flex items-center gap-2">
          <Avatar name="opus" letter="O" size={28} />
          <div className="flex-1">
            <div className="text-[14px] font-display font-semibold">Сообщение opus'у</div>
            <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              Оркестратор команды · claude-opus-4-7
            </div>
          </div>
          <button onClick={onClose} className="btn btn-ghost !p-1.5">
            <Icon.X size={14} />
          </button>
        </div>
        <Composer placeholder="Что поручить Opus? Можно /plan /ship /review…" />
        <div className="mt-2 text-[10.5px] text-center" style={{ color: "var(--text-muted)" }}>
          <kbd>Esc</kbd> закрыть · <kbd>⌘</kbd><kbd>↵</kbd> отправить
        </div>
      </div>
    </div>
  );
}
