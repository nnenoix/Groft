import React from 'react';

export type IconProps = { size?: number; stroke?: number; className?: string; style?: React.CSSProperties };

const I = ({ children, size = 16, stroke = 1.75, className = "", style = {} }: IconProps & { children: React.ReactNode }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size} height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={stroke}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
    aria-hidden="true"
  >
    {children}
  </svg>
);

export const Icon = {
  Users:      (p: IconProps) => <I {...p}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></I>,
  Check:      (p: IconProps) => <I {...p}><path d="M20 6 9 17l-5-5"/></I>,
  Chat:       (p: IconProps) => <I {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></I>,
  Cog:        (p: IconProps) => <I {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></I>,
  Terminal:   (p: IconProps) => <I {...p}><path d="M4 17l6-6-6-6"/><path d="M12 19h8"/></I>,
  Send:       (p: IconProps) => <I {...p}><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></I>,
  Hash:       (p: IconProps) => <I {...p}><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></I>,
  Link:       (p: IconProps) => <I {...p}><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></I>,
  Message:    (p: IconProps) => <I {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></I>,
  Plus:       (p: IconProps) => <I {...p}><path d="M12 5v14M5 12h14"/></I>,
  Search:     (p: IconProps) => <I {...p}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></I>,
  Play:       (p: IconProps) => <I {...p}><polygon points="6 3 20 12 6 21 6 3"/></I>,
  Pause:      (p: IconProps) => <I {...p}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></I>,
  Dot:        (p: IconProps) => <I {...p}><circle cx="12" cy="12" r="3" fill="currentColor"/></I>,
  Maximize:   (p: IconProps) => <I {...p}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></I>,
  Minimize:   (p: IconProps) => <I {...p}><path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/></I>,
  ArrowRight: (p: IconProps) => <I {...p}><path d="M5 12h14M13 5l7 7-7 7"/></I>,
  Code:       (p: IconProps) => <I {...p}><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></I>,
  Circle:     (p: IconProps) => <I {...p}><circle cx="12" cy="12" r="10"/></I>,
  CheckCircle:(p: IconProps) => <I {...p}><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></I>,
  Zap:        (p: IconProps) => <I {...p}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></I>,
  Activity:   (p: IconProps) => <I {...p}><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></I>,
  Brain:      (p: IconProps) => <I {...p}><path d="M9.5 2a2.5 2.5 0 0 1 2.5 2.5v15a2.5 2.5 0 1 1-5 0V18a2.5 2.5 0 0 1-2.5-2.5v-1a2.5 2.5 0 0 1-1-4.5A2.5 2.5 0 0 1 5 5.5 2.5 2.5 0 0 1 7 3a2.5 2.5 0 0 1 2.5-1z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 1 0 5 0V18a2.5 2.5 0 0 0 2.5-2.5v-1a2.5 2.5 0 0 0 1-4.5 2.5 2.5 0 0 0-.5-4.5A2.5 2.5 0 0 0 17 3a2.5 2.5 0 0 0-2.5-1z"/></I>,
  Layers:     (p: IconProps) => <I {...p}><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></I>,
  Heart:      (p: IconProps) => <I {...p}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></I>,
  X:          (p: IconProps) => <I {...p}><path d="M18 6 6 18M6 6l12 12"/></I>,
  ChevronDown:(p: IconProps) => <I {...p}><path d="m6 9 6 6 6-6"/></I>,
  ChevronRight:(p: IconProps) => <I {...p}><path d="m9 6 6 6-6 6"/></I>,
  Edit:       (p: IconProps) => <I {...p}><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></I>,
  Trash:      (p: IconProps) => <I {...p}><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></I>,
  Copy:       (p: IconProps) => <I {...p}><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></I>,
  Clock:      (p: IconProps) => <I {...p}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></I>,
  Waveform:   (p: IconProps) => <I {...p}><path d="M2 10v4M6 6v12M10 3v18M14 7v10M18 10v4M22 12v0"/></I>,
  Sun:        (p: IconProps) => <I {...p}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></I>,
  Moon:       (p: IconProps) => <I {...p}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></I>,
  Sliders:    (p: IconProps) => <I {...p}><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></I>,
  GitBranch:  (p: IconProps) => <I {...p}><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></I>,
  Command:    (p: IconProps) => <I {...p}><path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/></I>,
  Logo:       (p: IconProps) => (
    <svg xmlns="http://www.w3.org/2000/svg" width={p.size ?? 24} height={p.size ?? 24} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="7" cy="8" r="3.2" fill="currentColor" opacity="0.22"/>
      <circle cx="17" cy="8" r="3.2" fill="currentColor" opacity="0.22"/>
      <path d="M3 14a9 9 0 0 0 18 0 9 9 0 0 0-9-7 9 9 0 0 0-9 7Z" fill="currentColor" opacity="0.35"/>
      <circle cx="7" cy="8" r="1.4" fill="currentColor"/>
      <circle cx="17" cy="8" r="1.4" fill="currentColor"/>
      <circle cx="7" cy="8" r="0.55" fill="var(--bg-card)"/>
      <circle cx="17" cy="8" r="0.55" fill="var(--bg-card)"/>
    </svg>
  ),
};
