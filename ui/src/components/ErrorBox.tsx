export function ErrorBox({ message }: { message: string }) {
  return (
    <div
      className="mx-[var(--pad-6)] mt-[var(--pad-4)] px-3 py-2 rounded-md text-[12px]"
      style={{
        background: "rgba(239, 68, 68, 0.1)",
        color: "var(--status-stuck, #ef4444)",
        border: "1px solid var(--status-stuck, #ef4444)",
      }}
    >
      {message}
    </div>
  );
}
