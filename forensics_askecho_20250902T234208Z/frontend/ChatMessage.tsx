// File: components/AskAgent/ChatMessage.tsx
// Purpose: Render a single chat message bubble with normalized output.
//          Prefers final_text (already set by the hook) and supports error,
//          context (collapsible), meta/timings badges, and action status.
// Updated: 2025-09-02

"use client";

import React, { useMemo, useState } from "react";
import SafeMarkdown from "@/components/SafeMarkdown";
import { toMDString } from "@/lib/toMDString";
import MetaBadges, { type MetaBadge } from "@/components/common/MetaBadges";

type Props = {
  role: "user" | "assistant";
  content: unknown; // will be coerced to string safely
  error?: string | null;
  context?: string;
  /** meta may include { origin, timings_ms, request_id } */
  meta?: Record<string, unknown> | null;
  status?: "pending" | "approved" | "denied";
  isContextOpen?: boolean;
  onToggleContext?: () => void;
  showExtras?: boolean;
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
  const align = isUser ? "items-end text-right" : "items-start text-left";
  const bubbleTone = isUser ? "bg-blue-50 border-blue-200" : "bg-green-50 border-green-200";
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

  // Adapt the loose meta object into MetaBadge[]
  const metaItems: MetaBadge[] = useMemo(() => {
    const items: MetaBadge[] = [];
    if (!meta) return items;

    const origin = typeof meta.origin === "string" ? meta.origin : undefined;
    const requestId =
      typeof meta.request_id === "string"
        ? meta.request_id
        : typeof meta.requestId === "string"
        ? meta.requestId
        : undefined;

    const timings =
      typeof meta.timings_ms === "number"
        ? `${meta.timings_ms} ms`
        : typeof meta.latency_ms === "number"
        ? `${meta.latency_ms} ms`
        : undefined;

    if (origin) {
      items.push({ label: "Origin", value: origin, tone: "neutral", title: "response origin" });
    }
    if (timings) {
      items.push({ label: "Latency", value: timings, tone: "info", title: "end-to-end latency" });
    }
    if (requestId) {
      items.push({
        label: "ReqID",
        value: requestId,
        tone: "neutral",
        title: "request identifier",
        hideIfEmpty: true,
      });
    }

    // Include any extra meta keys (briefly), skip objects/arrays/functions
    Object.entries(meta).forEach(([k, v]) => {
      if (k === "origin" || k === "request_id" || k === "requestId" || k === "timings_ms" || k === "latency_ms") {
        return;
      }
      const isSimple =
        typeof v === "string" ||
        typeof v === "number" ||
        typeof v === "boolean" ||
        v === null ||
        v === undefined;
      if (isSimple) {
        items.push({
          label: k,
          value: v === undefined ? "" : String(v),
          tone: "neutral",
          hideIfEmpty: true,
        });
      }
    });

    return items;
  }, [meta]);

  // Error bubble (takes precedence over content)
  if (error) {
    return (
      <div className={`flex ${align} ${className}`}>
        <div className="w-fit max-w-[80ch] rounded-xl border border-red-200 bg-red-50 p-3 text-left shadow-sm">
          <div className="text-sm font-medium text-red-800">Request error</div>
          <div className="mt-1 break-words font-mono text-sm text-red-900">{error}</div>
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
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusChip status={status} />
          {metaItems.length > 0 && <MetaBadges items={metaItems} />}
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
