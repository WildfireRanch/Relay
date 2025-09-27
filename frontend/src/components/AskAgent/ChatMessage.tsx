// File: components/AskAgent/ChatMessage.tsx
// Purpose: Render a single chat message bubble with normalized output.
//          Extracts best string content safely (no `any`), supports error,
//          collapsible context, MetaBadges, and action status chips.
// Updated: 2025-09-04 (typed, any-free)

"use client";

import React, { useId, useMemo, useState } from "react";
import { toMDString } from "@/lib/toMDString";
import SafeMarkdown from "@/components/SafeMarkdown";
import MetaBadges, { type MetaBadge } from "@/components/common/MetaBadges";

type Role = "user" | "assistant";
type Status = "pending" | "approved" | "denied";

type Props = {
  role: Role;
  content: unknown;
  error?: string | null;
  context?: unknown;
  /** meta may include { origin, timings_ms, latency_ms, request_id, route, corr_id } */
  meta?: Record<string, unknown> | null;
  status?: Status;
  isContextOpen?: boolean;
  onToggleContext?: () => void;
  showExtras?: boolean;
  className?: string;
};

// -------- Type guards / helpers (any-free) ---------------------------------

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function getString(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function getNumber(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

/**
 * Safely extract the best user-facing string from heterogeneous content:
 * - string
 * - { routed_result: { response|answer } }
 * - { plan: { final_answer } }
 * - { response|answer } directly
 */
function extractFinalText(content: unknown): string {
  // Plain string
  if (typeof content === "string" && content.trim()) return content;

  // Object forms
  if (isRecord(content)) {
    // Prefer routed_result.response / answer
    const rr = content["routed_result"];
    if (isRecord(rr)) {
      const rrResp = getString(rr["response"]);
      if (rrResp && rrResp.trim()) return rrResp;
      const rrAns = getString(rr["answer"]);
      if (rrAns && rrAns.trim()) return rrAns;
    } else if (typeof rr === "string" && rr.trim()) {
      return rr;
    }

    // Next: direct response / answer on root
    const resp = getString(content["response"]);
    if (resp && resp.trim()) return resp;
    const ans = getString(content["answer"]);
    if (ans && ans.trim()) return ans;

    // Finally: plan.final_answer
    const plan = content["plan"];
    if (isRecord(plan)) {
      const fa = getString(plan["final_answer"]);
      if (fa && fa.trim()) return fa;
    }
  }

  return "";
}

/** Normalize meta into MetaBadges (no noisy object values). */
function metaToBadges(meta: Record<string, unknown> | null | undefined): MetaBadge[] {
  if (!meta) return [];
  const items: MetaBadge[] = [];

  const origin = getString(meta.origin) ?? getString(meta.route);
  const timings = isRecord(meta.timings_ms) ? getNumber(meta.timings_ms.total) : getNumber(meta.timings_ms);
  const latency = timings ?? getNumber(meta.latency_ms);
  const requestId =
    getString(meta.request_id) ??
    getString(meta.requestId) ??
    getString(meta["X-Request-Id"]) ??
    getString(meta.corr_id);

  if (origin) items.push({ label: "Origin", value: origin, tone: "neutral", title: "response origin" });
  if (typeof latency === "number") items.push({ label: "Latency", value: `${latency} ms`, tone: "info", title: "end-to-end latency" });
  if (requestId) items.push({ label: "ReqID", value: requestId, tone: "neutral", title: "request id", hideIfEmpty: true });

  // Include other primitives (skip standard keys & complex objects)
  for (const [k, v] of Object.entries(meta)) {
    if (["origin", "route", "request_id", "requestId", "latency_ms", "timings_ms", "corr_id", "X-Request-Id"].includes(k)) continue;
    const isPrimitive = v == null || ["string", "number", "boolean"].includes(typeof v);
    if (isPrimitive) items.push({ label: k, value: v == null ? "" : String(v), tone: "neutral", hideIfEmpty: true });
  }
  return items;
}

// -------- UI ---------------------------------------------------------------

function StatusChip({ status }: { status?: Status }) {
  if (!status) return null;
  const classes: Record<Status, string> = {
    pending: "bg-yellow-200 text-yellow-900",
    approved: "bg-emerald-200 text-emerald-900",
    denied: "bg-rose-200 text-rose-900",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes[status]}`}
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
  const isUser = role === "user";
  const align = isUser ? "items-end text-right" : "items-start text-left";
  const bubbleTone = isUser ? "bg-blue-50" : "bg-green-50";
  const textTone = isUser ? "text-blue-800" : "text-green-800";

  const [localOpen, setLocalOpen] = useState(false);
  const open = typeof isContextOpen === "boolean" ? isContextOpen : localOpen;
  const onToggle = () => (onToggleContext ? onToggleContext() : setLocalOpen((v) => !v));

  const ctxId = useId();

  const chosen: string | null = useMemo(() => {
    try {
      const picked = extractFinalText(content);
      return picked && picked.trim() ? picked : null;
    } catch {
      return null;
    }
  }, [content]);

  const md = useMemo(() => toMDString(chosen ?? content), [chosen, content]);
  const metaItems = useMemo(() => metaToBadges(meta), [meta]);

  // Error bubble takes precedence
  if (typeof error === "string" && error.length > 0) {
    return (
      <div className={`flex ${align} ${className}`}>
        <div className="w-fit max-w-[80ch] rounded-xl bg-red-50 p-3 text-left shadow-sm">
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
      <div className={`w-fit max-w-[80ch] rounded-xl p-3 text-left shadow-sm ${bubbleTone}`}>
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
                className="mt-1 rounded bg-background/60 p-2"
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
