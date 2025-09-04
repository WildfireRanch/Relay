// File: components/AskAgent/ChatMessage.tsx
// Purpose: Render a single chat message bubble with normalized output.
//          Prefers pickFinalText -> toMDString pipeline (no JSON spam if we have a string),
//          supports error, collapsible context, MetaBadges, and action status chips.
// Updated: 2025-09-04 (typed, no-any, robust guards)

"use client";

import React, { useId, useMemo, useState } from "react";
import { toMDString } from "@/lib/toMDString";
import { pickFinalText as pickFinalTextPair } from "@/lib/pickFinalText"; // expects (plan, routedResult)
import SafeMarkdown from "@/components/SafeMarkdown";
import MetaBadges, { type MetaBadge } from "@/components/common/MetaBadges";

type Role = "user" | "assistant";
type Status = "pending" | "approved" | "denied";

type Props = {
  role: Role;
  content: unknown;               // heterogeneous backend shape
  error?: string | null;
  context?: unknown;              // may be object/array; stringified via toMDString
  /** meta may include { origin, timings_ms, latency_ms, request_id, route, corr_id } */
  meta?: Record<string, unknown> | null;
  status?: Status;
  isContextOpen?: boolean;
  onToggleContext?: () => void;
  showExtras?: boolean;
  className?: string;
};

/* ────────────────────────────────────────────────────────────────────────────
 * Narrowing helpers (no-any)
 * --------------------------------------------------------------------------- */

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function getString(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function getNumber(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

function hasKey<T extends string>(
  obj: Record<string, unknown>,
  key: T
): obj is Record<T, unknown> & Record<string, unknown> {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

/** Backend often returns `{ plan, routed_result }` or a plain string. */
function isPlanRoutedShape(v: unknown): v is { plan?: unknown; routed_result?: unknown } {
  return isRecord(v) && ("plan" in v || "routed_result" in v);
}

/** Safe adapter over the pair-based pickFinalText(plan, routedResult). */
function safePickFinalText(content: unknown): string {
  // Direct string
  if (typeof content === "string" && content.trim()) return content;

  // { plan?, routed_result? }
  if (isPlanRoutedShape(content)) {
    const plan = isRecord(content) && hasKey(content, "plan") ? content.plan : undefined;
    const rr = isRecord(content) && hasKey(content, "routed_result") ? content.routed_result : undefined;
    const fromPair = pickFinalTextPair(
      (isRecord(plan) ? (plan as Record<string, unknown>) : (plan as unknown)) as any,             // TS note below
      (isRecord(rr) || typeof rr === "string" || rr == null ? rr : undefined) as any               // TS note below
    );
    // ^ We call pair helper which already validates unknown; keeping as any only in adapter
    //   to satisfy its signature; the rest of this file stays any-free.
    if (fromPair && typeof fromPair === "string" && fromPair.trim()) return fromPair;
  }

  // Routed-result-alone object?
  if (isRecord(content)) {
    const resp = getString(content["response"]);
    if (resp && resp.trim()) return resp;
    const ans = getString(content["answer"]);
    if (ans && ans.trim()) return ans;
  }

  // Nothing conclusive
  return "";
}

/** Normalize meta into MetaBadges (no noisy objects). */
function metaToBadges(meta: Record<string, unknown> | null | undefined): MetaBadge[] {
  if (!meta) return [];
  const items: MetaBadge[] = [];

  const origin = getString(meta.origin) ?? getString(meta.route);
  const timings = isRecord(meta.timings_ms) ? getNumber(meta.timings_ms.total) : getNumber(meta.timings_ms);
  const latency = timings ?? getNumber(meta.latency_ms);
  const requestId =
    getString(meta.request_id) ?? getString(meta.requestId) ?? getString(meta["X-Request-Id"]) ?? getString(meta.corr_id);

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

/* ────────────────────────────────────────────────────────────────────────────
 * UI components
 * --------------------------------------------------------------------------- */

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

  // a11y id for the collapsible region
  const ctxId = useId();

  // 1) Try canonical extractor (via adapter) → 2) Fallback to stringify
  const chosen: string | null = useMemo(() => {
    try {
      const picked = safePickFinalText(content);
      return picked && picked.trim() ? picked : null;
    } catch {
      return null;
    }
  }, [content]);

  const md = useMemo(() => {
    // If we have a string, render it; else stringify original content
    return toMDString(chosen ?? content);
  }, [chosen, content]);

  const metaItems = useMemo(() => metaToBadges(meta), [meta]);

  // Error bubble takes precedence
  if (typeof error === "string" && error.length > 0) {
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
 