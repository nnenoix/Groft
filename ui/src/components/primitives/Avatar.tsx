export const AVATAR_BG: Record<string, string> = {
  opus:           "oklch(0.72 0.13 45)",
  "backend-dev":  "oklch(0.68 0.09 180)",
  "frontend-dev": "oklch(0.72 0.11 280)",
  tester:         "oklch(0.74 0.10 130)",
  reviewer:       "oklch(0.70 0.09 330)",
  "docs-writer":  "oklch(0.75 0.08 80)",
};

interface AvatarProps {
  name: string;
  letter?: string;
  size?: number;
}

export function Avatar({ name, letter, size = 32 }: AvatarProps) {
  const bg = AVATAR_BG[name] ?? "var(--accent-primary)";
  return (
    <div
      className="flex items-center justify-center rounded-full text-white font-semibold shrink-0 font-display"
      style={{ width: size, height: size, background: bg, fontSize: size * 0.4 }}
    >
      {letter ?? name[0]?.toUpperCase()}
    </div>
  );
}
