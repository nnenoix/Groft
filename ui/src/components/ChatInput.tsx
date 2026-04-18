import { useState, type KeyboardEvent } from "react";

export interface ChatInputProps {
  /**
   * Called with the trimmed text. Return `true` if the message was dispatched
   * (e.g. WebSocket send succeeded) so the textarea can be cleared. Return
   * `false` to keep the text and flag an error state in the UI.
   */
  onSubmit: (text: string) => boolean;
}

function ChatInput({ onSubmit }: ChatInputProps) {
  const [text, setText] = useState("");
  const [hasError, setHasError] = useState(false);

  function handleSubmit() {
    // Any new send attempt clears the prior error flag.
    setHasError(false);
    const trimmed = text.trim();
    if (!trimmed) return;
    const ok = onSubmit(trimmed);
    if (ok) {
      setText("");
    } else {
      setHasError(true);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const borderClass = hasError
    ? "border-status-stuck focus:border-status-stuck"
    : "border-border focus:border-accent-primary";

  return (
    <div className="h-full p-4 flex flex-col gap-2">
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (hasError) setHasError(false);
        }}
        onKeyDown={handleKeyDown}
        placeholder="Опиши задачу для Opus..."
        className={`flex-1 bg-bg-card border ${borderClass} rounded-lg p-3 text-sm text-text-primary placeholder-text-dim resize-none focus:outline-none transition-colors`}
      />
      {hasError && (
        <div className="text-status-stuck text-xs">
          Сообщение не отправлено — нет связи
        </div>
      )}
      <button
        type="button"
        onClick={handleSubmit}
        className="bg-accent-primary hover:bg-accent-hover text-bg-card font-medium px-4 py-2 rounded-lg transition-colors self-end text-sm"
      >
        Отправить
      </button>
    </div>
  );
}

export default ChatInput;
