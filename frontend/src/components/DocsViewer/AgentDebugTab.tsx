// File: components/DocsViewer/AgentDebugTab.tsx
// Purpose: DocsViewer debug tab that POSTs to /ask (normalized contract) to preview
//          the model's final_text and inspect injected context/meta.
// Updated: 2025-09-02
//
// Usage (inside DocsViewer):
//   <AgentDebugTab initialQuery="Summarize this doc" defaultRole="docs" files={[currentPath]} />
//
// Notes:
// - final_text is the primary UI answer; plan.final_answer and routed_result.response are fallbacks.
// - debug=true returns context/meta; context is shown behind a toggle.
// - Optional `files` lets you bind the active doc(s) so the backend can inject them into context.

"use client";

import React, { useCallback, useRef, useState } from "react";
import { API_ROOT } from "@/lib/api";
import SafeMarkdown from "@/components/SafeMarkdown";
import { toMDString } from "@/lib/toMDString";
import MetaBadges from "@/components/common/MetaBadges";

type AskResponse = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?: { response?: unknown; answer?: unknown } | string | null;
  context?: string;
  meta?: Record<string, unknown> | null;
};

type Role = "docs" | "planner" | "codex" | "control";

type Props = {
  initialQuery?: string;
  defaultRole?: Role;
  files?: string[];    // e.g., ["/docs/sol-ark.md"] (optional)
  topics?: string[];   // optional tags that your backend recognizes
  userId?: string;     // override X-User-Id if needed
};

const USER_ID = "bret-demo";

// ---- helpers ---------------------------------------------------------------

function pickFinalText(data: unknown): string {
  const d = (data as { result?: AskResponse })?.result ?? (data as AskResponse);
  const fromRR =
    typeof d?.routed_result === "string"
      ? d.routed_result
      : (d?.routed_result as { response?: unknown; answer?: unknown } | null | undefined)?.response ??
        (d?.routed_result as { response?: unknown; answer?: unknown } | null | undefined)?.answer;

  return (
    (typeof d?.final_text === "string" && d.final_text) ||
    (typeof d?.plan?.final_answer === "string" && d.plan.final_answer) ||
    (typeof fromRR === "string" && fromRR) ||
    ""
  );
}

async function extractHttpError(res: Response): Promise<string> {
  try {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = (await res.json()) as Record<string, unknown>;
      const msg =
        (j?.error as { message?: string } | undefined)?.message ||
        (j?.message as string | undefined) ||
        (j?.detail as string | undefined) ||
        (j?.error as string | undefined) ||
        JSON.stringify(j);
      return `HTTP ${res.status} ${res.statusText} — ${msg}`;
    }
    const t = await res.text();
    return `HTTP ${res.status} ${res.statusText} — ${t.slice(0, 800)}`;
  } catch {
    return `HTTP ${res.status} ${res.statusText}`;
  }
}

// ---- component -------------------------------------------------------------

export default function AgentDebugTab({
  initialQuery = "",
  defaultRole = "docs",
  files = [],
  topics = [],
  userId = USER_ID,
}: Props) {
  const [query, setQuery] = useState<string>(initialQuery);
  const [role, setRole] = useState<Role>(defaultRole);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string>("");
  const [context, setContext] = useState<string>("");
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [showCtx, setShowCtx] = useState<boolean>(false);
  const formRef = useRef<HTMLFormElement>(null);

  const onAsk = useCallback(async () => {
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setAnswer("");
    setContext("");
    setMeta(null);
    setShowCtx(false);

    try {
      const res = await fetch(`${API_ROOT}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          query: q,
          files,
          topics,
          role,       // "docs" by default so your backend injects KB/doc context
          debug: true // request context/meta for inspection
        }),
      });

      if (!res.ok) {
        setError(await extractHttpError(res));
        return;
      }

      const data = (await res.json()) as AskResponse | { result?: AskResponse };
      setAnswer(toMDString(pickFinalText(data)));

      const ctx =
        (data as AskResponse)?.context ??
        (data as { result?: AskResponse })?.result?.context ??
        "";
      setContext(toMDString(typeof ctx === "string" ? ctx : ""));

      const m =
        (data as AskResponse)?.meta ??
        (data as { result?: AskResponse })?.result?.meta ??
        null;
      setMeta(m ?? null);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : typeof err === "string" ? err : "Unknown error";
      setError(`Network error: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [query, files, topics, role, loading, userId]);

  return (
    <section className="space-y-3">
      {/* Controls */}
      <form
        ref={formRef}
        className="grid grid-cols-1 gap-2 md:grid-cols-5"
        onSubmit={(e) => {
          e.preventDefault();
          void onAsk();
        }}
      >
        <label className="md:col-span-3 flex flex-col text-sm">
          <span className="mb-1 font-medium">Ask about this doc</span>
          <input
            className="rounded border bg-background px-3 py-2"
            placeholder="e.g., Summarize the key actions and risks"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
            name="ask-query"
            id="ask-query"
            aria-label="Ask about this document"
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="mb-1 font-medium">Role</span>
          <select
            className="rounded border bg-background px-2 py-2"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            disabled={loading}
            aria-label="Agent role"
          >
            <option value="docs">docs</option>
            <option value="planner">planner</option>
            <option value="codex">codex</option>
            <option value="control">control</option>
          </select>
        </label>

        <div className="flex items-end">
          <button
            type="submit"
            className="rounded px-4 py-2 text-sm border shadow-sm disabled:opacity-50"
            disabled={loading || !query.trim()}
            aria-busy={loading}
          >
            {loading ? "Asking…" : "Ask"}
          </button>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          <div className="font-medium">Request error</div>
          <div className="mt-1 break-words font-mono">{error}</div>
        </div>
      )}

      {/* Answer preview */}
      <div className="rounded-xl border bg-card p-4">
        <div className="mb-2 text-xs text-muted-foreground">Answer (final_text)</div>
        <div className="prose prose-neutral dark:prose-invert max-w-none">
          <SafeMarkdown>{answer}</SafeMarkdown>
        </div>
        <MetaBadges meta={meta} />
      </div>

      {/* Context (debug) */}
      {!!context && (
        <div className="rounded-xl border bg-card/60 p-4">
          <button
            type="button"
            onClick={() => setShowCtx((v) => !v)}
            className="text-xs underline underline-offset-2"
            aria-expanded={showCtx}
            aria-controls="agent-context"
          >
            {showCtx ? "Hide injected context" : "Show injected context"}
          </button>
          {showCtx && (
            <div id="agent-context" className="prose prose-sm prose-neutral dark:prose-invert mt-2 max-w-none">
              <SafeMarkdown>{context}</SafeMarkdown>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
