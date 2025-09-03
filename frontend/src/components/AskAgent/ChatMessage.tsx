// File: components/AskAgent/ChatMessage.tsx
// Purpose: Render a single chat message bubble with normalized output.
//          Prefers pickFinalText -> toMDString pipeline (no JSON spam if we have a string),
//          supports error, collapsible context, MetaBadges, and action status chips.
// Updated: 2025-09-02

"use client";

import React, { useId, useMemo, useState } from "react";
import { toMDString } from "@/lib/toMDString";
import { pickFinalText } from "@/lib/pickFinalText";
import SafeMarkdown from "@/components/SafeMarkdown";
import MetaBadges, { type MetaBadge } from "@/components/common/MetaBadges";

type Role = "user" | "assistant";
type Status = "pending" | "approved" | "denied";

type Props = {
  role: Role;
  content: unknown; // will be coerced safely
  error?: string | null;
  context?: unknown; // allow object/array; we stringify via toMDString
  /** meta may include { origin, timings_ms, latency_ms, request_id } */
  meta?: Record<string, unknown> | null;
  status?: Status;
  isContextOpen?: boolean;
  onToggleContext?: () => void;
  showExtras?: boolean;
  className?: string;
};

function StatusChip({ status }: { status?: Status }) {
  if (!status) return null;
  const classes: Record<Status, string> = {
    pending: "bg-yellow-200 text-yellow-900 border-yellow-300",
    approved: "bg-emerald-200 text-emerald-900 border-emerald-300",
    denied: "bg-rose-200 text-rose-900 border-rose-300",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${classes[status]}`}
      aria-label={`status: ${status}`}
      title={`status: ${status}`}
      data-testid="status-chip"
    >
      {status}
    </span>
  );
}

export default function ChatMessage({
  role,
  content,
  error = null,
  context,
  meta = null,
  status,
  isContextOpen,
  onToggleContext,
  showExtras = true,
  className = "",
}: Props) {
  // Layout & tone
  const isUser = role === "user";
  const align = isUser ? "items-end text-right" : "items-start text-left";
  const bubbleTone = isUser ? "bg-blue-50 border-blue-200" : "bg-green-50 border-green-200";
  const textTone = isUser ? "text-blue-800" : "text-green-800";

  // Context toggle (controlled or uncontrolled)
  const [localOpen, setLocalOpen] = useState(false);
  const open = typeof isContextOpen === "boolean" ? isContextOpen : localOpen;
  const onToggle = () => (onToggleContext ? onToggleContext() : setLocalOpen((v) => !v));

  // a11y ids for the collapsible region
  const ctxId = useId();

  // 1) Prefer canonical extractor → 2) Fallback to your existing fence/JSON logic
  const chosen = useMemo(() => {
    try {
      const picked = pickFinalText(content as any);
      if (picked && typeof picked === "string") return picked;
      // If pickFinalText didn’t yield a string, we keep original content to stringify below.
      return content as any;
    } catch {
      return content as any;
    }
  }, [content]);

  const md = useMemo(() => {
    // If chosen is a string, render it; else stringify the original shape.
    if (typeof chosen === "string") return toMDString(chosen);
    return toMDString(content);
  }, [chosen, content]);

  // Normalize meta → MetaBadge[]
  const metaItems: MetaBadge[] = useMemo(() => {
    if (!meta) return [];
    const items: MetaBadge[] = [];

    const origin =
      typeof meta.origin === "string"
        ? meta.origin
        : typeof (meta as any).route === "string"
        ? String((meta as any).route)
        : undefined;

    // timings could be a number OR an object with total/planner/routed
    let latency: string | undefined;
    const t = (meta as any).timings_ms;
    if (typeof t === "number") latency = `${t} ms`;
    else if (t && typeof t === "object" && typeof t.total === "number") latency = `${t.total} ms`;
    else if (typeof (meta as any).latency_ms === "number") latency = `${(meta as any).latency_ms} ms`;

    const requestId =
      typeof (meta as any).request_id === "string"
        ? String((meta as any).request_id)
        : typeof (meta as any).requestId === "string"
        ? String((meta as any).requestId)
        : undefined;

    if (origin) items.push({ label: "Origin", value: origin, tone: "neutral", title: "response origin" });
    if (latency) items.push({ label: "Latency", value: latency, tone: "info", title: "end-to-end latency" });
    if (requestId) items.push({ label: "ReqID", value: requestId, tone: "neutral", title: "request id", hideIfEmpty: true });

    // Fold in any other primitive meta (skip noisy complex objects)
    for (const [k, v] of Object.entries(meta)) {
      if (["origin", "route", "request_id", "requestId", "timings_ms", "latency_ms"].includes(k)) continue;
      const isPrimitive = ["string", "number", "boolean"].includes(typeof v) || v == null;
      if (isPrimitive) items.push({ label: k, value: v == null ? "" : String(v), tone: "neutral", hideIfEmpty: true });
    }

    return items;
  }, [meta]);

  // Error bubble takes precedence
  if (error) {
    return (
      <div className={`flex ${align} ${className}`}>
        <div className="w-fit max-w-[80ch] rounded-xl border border-red-200 bg-red-50 p-3 text-left shadow-sm">
          <div className="text-sm font-semibold text-red-800">Request error</div>
          <div className="mt-1 break-words font-mono text-sm text-red-900" data-testid="error-text">
            {error}
          </div>
          {metaItems.length > 0 && (
            <div className="mt-2">
              <MetaBadges items={metaItems} />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${align} ${className}`}>
      <div className={`w-fit max-w-[80ch] rounded-xl border p-3 text-left shadow-sm ${bubbleTone}`}>
        {/* Main content */}
        <div className={`prose prose-neutral dark:prose-invert max-w-none ${textTone}`}>
          <SafeMarkdown>{md}</SafeMarkdown>
        </div>

        {/* Status + meta badges */}
        {(status || metaItems.length > 0) && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusChip status={status} />
            {metaItems.length > 0 && <MetaBadges items={metaItems} />}
          </div>
        )}

        {/* Collapsible debug/context */}
        {showExtras && context != null && String(context).length > 0 && (
          <div className="mt-2">
            <button
              type="button"
              onClick={onToggle}
              className="text-xs underline underline-offset-2 hover:opacity-80"
              aria-expanded={open}
              aria-controls={ctxId}
              data-testid="ctx-toggle"
            >
              {open ? "Hide context" : "Show context"}
            </button>
            {open && (
              <div
                id={ctxId}
                className="mt-1 rounded border bg-background/60 p-2"
                role="region"
                aria-label="message context"
              >
                <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none">
                  <SafeMarkdown>{toMDString(context)}</SafeMarkdown>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
