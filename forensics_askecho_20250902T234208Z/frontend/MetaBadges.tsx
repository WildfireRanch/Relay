// File: src/components/common/MetaBadges.tsx
import React, { useMemo } from "react";
import clsx from "clsx";

type Tone = "info" | "success" | "warning" | "danger" | "neutral";

export interface MetaBadge {
  /** Main text shown in the badge */
  label: string;
  /** Optional value (e.g., count or short text) */
  value?: string | number;
  /** Optional link target */
  href?: string;
  /** Optional leading icon */
  icon?: React.ReactNode;
  /** Visual tone */
  tone?: Tone;
  /** Optional title/tooltip */
  title?: string;
  /** Hide badge if value is empty/undefined */
  hideIfEmpty?: boolean;
}

export interface MetaBadgesProps {
  items: MetaBadge[];
  className?: string;
  /** Limit the number of visible badges */
  max?: number;
}

function toneClasses(tone: Tone = "neutral") {
  switch (tone) {
    case "info":
      return "bg-blue-50 text-blue-800 ring-blue-200";
    case "success":
      return "bg-green-50 text-green-800 ring-green-200";
    case "warning":
      return "bg-yellow-50 text-yellow-900 ring-yellow-200";
    case "danger":
      return "bg-red-50 text-red-800 ring-red-200";
    default:
      return "bg-gray-50 text-gray-800 ring-gray-200";
  }
}

export default function MetaBadges({ items, className, max }: MetaBadgesProps) {
  // Always call hooks unconditionally
  const filtered = useMemo(() => {
    return (items ?? []).filter((b) =>
      b.hideIfEmpty ? b.value !== undefined && b.value !== "" : true
    );
  }, [items]);

  const visible = useMemo(() => {
    if (typeof max === "number" && max >= 0) return filtered.slice(0, max);
    return filtered;
  }, [filtered, max]);

  if (!visible.length) return null;

  return (
    <div className={clsx("flex flex-wrap gap-2", className)}>
      {visible.map((b, idx) => {
        const content = (
          <span
            className={clsx(
              "inline-flex items-center gap-1 rounded-2xl px-2.5 py-1 text-xs ring-1",
              toneClasses(b.tone)
            )}
            title={b.title}
          >
            {b.icon ? <span className="shrink-0">{b.icon}</span> : null}
            <span className="font-medium">{b.label}</span>
            {b.value !== undefined && b.value !== "" ? (
              <span className="opacity-80">· {b.value}</span>
            ) : null}
          </span>
        );

        return b.href ? (
          <a key={`${b.label}-${idx}`} href={b.href} target="_blank" rel="noreferrer">
            {content}
          </a>
        ) : (
          <div key={`${b.label}-${idx}`}>{content}</div>
        );
      })}
    </div>
  );
}
