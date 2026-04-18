import React from "react";

type ChipTone = "default" | "accent" | "ok" | "warn" | "danger";

interface ChipProps {
  tone?: ChipTone;
  children: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export function Chip({ tone = "default", children, icon, className = "" }: ChipProps) {
  const cls = tone === "default" ? "chip" : `chip ${tone}`;
  return (
    <span className={`${cls} ${className}`}>
      {icon && icon}
      {children}
    </span>
  );
}
