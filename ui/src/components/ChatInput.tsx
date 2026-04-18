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
    <div className="flex flex-col gap-2 p-3 h-full">
      <textarea
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Опиши задачу для Opus..."
        className="flex-1 resize-none bg-card text-white rounded-md p-2 text-sm outline-none border border-[#222] focus:border-accent"
      />
      <button
        type="button"
        onClick={handleSubmit}
        className="bg-accent text-black font-semibold text-sm py-2 px-3 rounded-md self-end hover:opacity-90"
      >
        Отправить
      </button>
    </div>
  );
}

export default ChatInput;
