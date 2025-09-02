// File: components/AskAgent/ChatMessage.tsx
// Purpose: Render a single chat message bubble with normalized output.
//          Prefers final_text (already set by the hook) and supports error,
//          context (collapsible), meta/timings badges, and action status.
// Updated: 2025-09-02
//
// Notes:
// - Backward compatible: only `role` and `content` are required.
// - If `error` is provided, we render an error bubble instead of content.
// - `context` is optional; can be toggled via controlled props or internal state.
// - `meta` may include { origin, timings_ms, request_id } — displayed compactly.
// - `status` can be "pending" | "approved" | "denied" for action flow UI.

"use client";

import React, { useMemo, useState } from "react";
import SafeMarkdown from "@/components/SafeMarkdown";
import { toMDString } from "@/lib/toMDString";

type Props = {
  role: "user" | "assistant";
  content: unknown;                         // will be coerced to string safely
  error?: string | null;                    // optional error text (renders a red bubble)
  context?: string;                         // optional debug/context markdown
  meta?: Record<string, any> | null;        // optional meta (origin, timings_ms, request_id)
  status?: "pending" | "approved" | "denied";
  // Controlled context toggle (optional). If not provided, component manages its own.
  isContextOpen?: boolean;
  onToggleContext?: () => void;
  showExtras?: boolean;                     // gate for context/meta display; defaults true
  className?: string;
};

function StatusChip({ status }: { status?: Props["status"] }) {
  if (!status) return null;
  const map: Record<string, string> = {
    pending: "bg-yellow-200 text-yellow-900 border-yellow-300",
    approved: "bg-emerald-200 text-emerald-900 border-emerald-300",
    denied: "bg-rose-200 text-rose-900 border-rose-300",
  };
  const cls = map[status] ?? "bg-gray-200 text-gray-900 border-gray-300";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}
      aria-label={`status: ${status}`}
      title={`status: ${status}`}
    >
      {status}
    </span>
  );
}

function MetaBadges({ meta }: { meta?: Props["meta"] }) {
  if (!meta) return null;

  // Common fields: origin, request_id, timings_ms.{ttfb,total,...}
  const origin = (meta as any)?.origin as string | undefined;
  const requestId = (meta as any)?.request_id as string | undefined;
  const timings = (meta as any)?.timings_ms as Record<string, number> | undefined;

  const timingPairs = useMemo(() => {
    if (!timings || typeof timings !== "object") return [];
    // Show a compact subset, if present
    const keys = ["ttfb", "total", "latency", "plan", "route"];
    const pairs: Array<[string, number]> = [];
    for (const k of keys) {
      if (typeof timings[k] === "number") pairs.push([k, timings[k]]);
    }
    // Fallback: if empty, show first few entries
    if (pairs.length === 0) {
      for (const [k, v] of Object.entries(timings).slice(0, 3)) {
        if (typeof v === "number") pairs.push([k, v]);
      }
    }
    return pairs;
  }, [timings]);

  return (
    <div className="flex flex-wrap items-center gap-2 mt-1">
      {origin ? (
        <span className="rounded border bg-muted px-2 py-0.5 text-xs font-mono">
          origin: {origin}
        </span>
      ) : null}
      {requestId ? (
        <span className="rounded border bg-muted px-2 py-0.5 text-xs font-mono" title={requestId}>
          req: {requestId.length > 10 ? `${requestId.slice(0, 10)}…` : requestId}
        </span>
      ) : null}
      {timingPairs.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {timingPairs.map(([k, v]) => (
            <span key={k} className="rounded border bg-muted px-2 py-0.5 text-xs font-mono">
              {k}:{Math.round(v)}ms
            </span>
          ))}
        </div>
      )}
    </div>
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
  // Visual alignment / tone
  const isUser = role === "user";
  const align =
    isUser ? "items-end text-right" : "items-start text-left";
  const bubbleTone = isUser
    ? "bg-blue-50 border-blue-200"
    : "bg-green-50 border-green-200";
  const textTone = isUser ? "text-blue-800" : "text-green-800";

  // Internal toggle if a controlled prop isn't provided
  const [localOpen, setLocalOpen] = useState(false);
  const open = typeof isContextOpen === "boolean" ? isContextOpen : localOpen;
  const toggle = () => {
    if (onToggleContext) onToggleContext();
    else setLocalOpen((v) => !v);
  };

  // Coerce content to markdown-safe string
  const md = toMDString(content);

  // Error bubble (takes precedence over content)
  if (error) {
    return (
      <div className={`flex ${align} ${className}`}>
        <div className="max-w-[80ch] w-fit rounded-xl border bg-red-50 border-red-200 p-3 text-left shadow-sm">
          <div className="text-red-800 text-sm font-medium">Request error</div>
          <div className="mt-1 text-red-900 text-sm font-mono break-words">{error}</div>
          <MetaBadges meta={meta} />
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${align} ${className}`}>
      <div
        className={`max-w-[80ch] w-fit rounded-xl border p-3 text-left shadow-sm ${bubbleTone}`}
      >
        {/* Main content */}
        <div className={`prose prose-neutral dark:prose-invert max-w-none ${textTone}`}>
          <SafeMarkdown>{md}</SafeMarkdown>
        </div>

        {/* Status + meta badges */}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusChip status={status} />
          <MetaBadges meta={meta} />
        </div>

        {/* Context (debug) */}
        {showExtras && !!context && (
          <div className="mt-2">
            <button
              type="button"
              onClick={toggle}
              className="text-xs underline underline-offset-2 hover:opacity-80"
              aria-expanded={open}
              aria-controls="ctx"
            >
              {open ? "Hide context" : "Show context"}
            </button>
            {open && (
              <div id="ctx" className="mt-1 rounded border bg-background/60 p-2">
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
