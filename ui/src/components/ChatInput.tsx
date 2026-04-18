import { useState, type KeyboardEvent } from "react";

export interface ChatInputProps {
  onSubmit: (text: string) => void;
}

function ChatInput({ onSubmit }: ChatInputProps) {
  const [text, setText] = useState("");

  function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setText("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="p-4 flex flex-col gap-2 h-full">
      <textarea
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Опиши задачу для Opus..."
        className="flex-1 bg-bg-card border border-border rounded-lg p-3 text-text-primary placeholder-text-muted resize-none focus:outline-none focus:border-accent-primary transition-colors text-sm"
      />
      <button
        type="button"
        onClick={handleSubmit}
        className="bg-accent-primary hover:bg-accent-hover text-bg-primary font-medium px-4 py-2 rounded-lg transition-colors self-end"
      >
        Отправить
      </button>
    </div>
  );
}

export default ChatInput;
