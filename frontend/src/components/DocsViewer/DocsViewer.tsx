// File: frontend/src/components/DocsViewer.tsx
// Purpose: Browse, manage, and debug semantic context docs with tier-aware metadata.
//          Agent Context tab POSTs to /ask (normalized contract) and renders
//          final_text (with fallbacks), context (debug), and meta/timings.
// Updated: 2025-09-02

"use client";

import { API_ROOT } from "@/lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { toMDString } from "@/lib/toMDString";
import SafeMarkdown from "@/components/SafeMarkdown";
import MetaBadges, { type MetaBadge } from "@/components/common/MetaBadges";

// --- Types for KB docs and semantic search ---
type KBMeta = {
  path: string;
  doc_id?: string;
  tier?: string;
  source?: string;
  last_modified?: string;
};

type KBHit = {
  file?: string;
  snippet: string;
  score?: number;
  type?: string;
  line?: number;
};

// --- Normalized /ask response ---
type AskResponse = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?: { response?: unknown; answer?: unknown } | string | null;
  context?: string;
  meta?: Record<string, unknown> | null;
};

type Role = "docs" | "planner" | "codex" | "control";

// ---- helpers for Agent Context tab -----------------------------------------

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

// ----------------------------------------------------------------------------

const apiUrl = API_ROOT || "";
const USER_ID = "bret-demo";

// --- Main DocsViewer Component ---
export default function DocsViewer() {
  const [tab, setTab] = useState<"docs" | "search" | "context">("docs");

  // docs tab
  const [docs, setDocs] = useState<KBMeta[]>([]);
  const [activeDoc, setActiveDoc] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");

  // search tab
  const [search, setSearch] = useState<string>("");
  const [hits, setHits] = useState<KBHit[]>([]);
  const [selectedHit, setSelectedHit] = useState<number | null>(null);
  const [searchLoading, setSearchLoading] = useState<boolean>(false);

  // context tab (normalized /ask)
  const [ctxQuestion, setCtxQuestion] = useState<string>("");
  const [ctxLoading, setCtxLoading] = useState<boolean>(false);
  const [ctxError, setCtxError] = useState<string | null>(null);
  const [ctxAnswer, setCtxAnswer] = useState<string>("");
  const [ctxContext, setCtxContext] = useState<string>("");
  const [ctxMeta, setCtxMeta] = useState<Record<string, unknown> | null>(null);
  const [ctxShow, setCtxShow] = useState<boolean>(false);
  const [ctxRole, setCtxRole] = useState<Role>("docs");

  useEffect(() => {
    if (tab === "docs") {
      void loadDocs();
    }
  }, [tab]);

  useEffect(() => {
    if (activeDoc) {
      void loadContent(activeDoc);
    } else {
      setContent("");
    }
  }, [activeDoc]);

  async function loadDocs() {
    try {
      const res = await fetch(`${apiUrl}/docs/list`);
      const data = (await res.json()) as { files?: KBMeta[] };
      setDocs(Array.isArray(data.files) ? data.files : []);
    } catch {
      setDocs([]);
    }
  }

  async function loadContent(path: string) {
    try {
      const res = await fetch(`${apiUrl}/docs/view?path=${encodeURIComponent(path)}`);
      const data = (await res.json()) as { content?: string };
      setContent(typeof data.content === "string" ? data.content : "");
    } catch {
      setContent("Failed to load doc.");
    }
  }

  async function doSearch(e?: React.FormEvent) {
    if (e) e.preventDefault();
    setSearchLoading(true);
    setHits([]);
    setSelectedHit(null);
    try {
      const res = await fetch(`${apiUrl}/kb/search?query=${encodeURIComponent(search)}`);
      const data = (await res.json()) as { results?: KBHit[] };
      setHits(Array.isArray(data.results) ? data.results : []);
    } catch {
      setHits([]);
    }
    setSearchLoading(false);
  }

  // --- Normalized Agent Context: POST /ask with debug=true ---
  const fetchContextForPrompt = useCallback(
    async (e?: React.FormEvent) => {
      if (e) e.preventDefault();
      const q = ctxQuestion.trim();
      if (!q) return;

      setCtxLoading(true);
      setCtxError(null);
      setCtxAnswer("");
      setCtxContext("");
      setCtxMeta(null);
      setCtxShow(false);

      try {
        const res = await fetch(`${apiUrl}/ask`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": USER_ID,
          },
          body: JSON.stringify({
            query: q,
            files: activeDoc ? [activeDoc] : [],
            topics: [],
            role: ctxRole, // default "docs"
            debug: true, // return context/meta
          }),
        });

        if (!res.ok) {
          setCtxError(await extractHttpError(res));
          return;
        }

        const data = (await res.json()) as AskResponse | { result?: AskResponse };
        setCtxAnswer(toMDString(pickFinalText(data)));

        const ctx =
          (data as AskResponse)?.context ??
          (data as { result?: AskResponse })?.result?.context ??
          "";
        setCtxContext(toMDString(typeof ctx === "string" ? ctx : ""));

        const meta =
          (data as AskResponse)?.meta ??
          (data as { result?: AskResponse })?.result?.meta ??
          null;
        setCtxMeta(meta ?? null);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : typeof err === "string" ? err : "Unknown error";
        setCtxError(`Network error: ${msg}`);
      } finally {
        setCtxLoading(false);
      }
    },
    [ctxQuestion, activeDoc, ctxRole]
  );

  // --- Meta → MetaBadge[] adapter (unconditional hook) ----------------------
  const ctxMetaItems: MetaBadge[] = useMemo(() => {
    const items: MetaBadge[] = [];
    if (!ctxMeta) return items;

    const origin = typeof ctxMeta.origin === "string" ? ctxMeta.origin : undefined;
    const requestId =
      typeof (ctxMeta as Record<string, unknown>)["request_id"] === "string"
        ? (ctxMeta as Record<string, unknown>)["request_id"] as string
        : typeof (ctxMeta as Record<string, unknown>)["requestId"] === "string"
        ? (ctxMeta as Record<string, unknown>)["requestId"] as string
        : undefined;

    const latencyVal =
      typeof (ctxMeta as Record<string, unknown>)["timings_ms"] === "number"
        ? ((ctxMeta as Record<string, unknown>)["timings_ms"] as number)
        : typeof (ctxMeta as Record<string, unknown>)["latency_ms"] === "number"
        ? ((ctxMeta as Record<string, unknown>)["latency_ms"] as number)
        : undefined;
    const latency = latencyVal !== undefined ? `${latencyVal} ms` : undefined;

    if (origin) items.push({ label: "Origin", value: origin, tone: "neutral", title: "response origin" });
    if (latency) items.push({ label: "Latency", value: latency, tone: "info", title: "end-to-end latency" });
    if (requestId)
      items.push({ label: "ReqID", value: requestId, tone: "neutral", title: "request identifier", hideIfEmpty: true });

    // Include other simple meta entries (skip objects/arrays/functions and known keys)
    for (const [k, v] of Object.entries(ctxMeta)) {
      if (["origin", "request_id", "requestId", "timings_ms", "latency_ms"].includes(k)) continue;
      const isSimple =
        typeof v === "string" || typeof v === "number" || typeof v === "boolean" || v == null;
      if (isSimple) {
        items.push({
          label: k,
          value: v == null ? "" : String(v),
          tone: "neutral",
          hideIfEmpty: true,
        });
      }
    }

    return items;
  }, [ctxMeta]);

  return (
    <div className="max-w-5xl mx-auto py-6">
      <div className="mb-4 flex gap-4">
        <Button
          variant={tab === "docs" ? "default" : "outline"}
          onClick={() => setTab("docs")}
        >
          📝 Docs
        </Button>
        <Button
          variant={tab === "search" ? "default" : "outline"}
          onClick={() => setTab("search")}
        >
          🔍 Semantic Search
        </Button>
        <Button
          variant={tab === "context" ? "default" : "outline"}
          onClick={() => setTab("context")}
        >
          🧠 Agent Context
        </Button>
      </div>

      {tab === "docs" && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-6">
          <div className="col-span-1 space-y-4">
            <div>
              <div className="mb-2 font-semibold">Knowledge Base Files</div>
              <ul className="max-h-80 space-y-1 overflow-y-auto text-xs">
                {docs.map((doc) => (
                  <li key={doc.path}>
                    <button
                      className={`w-full rounded px-2 py-1 text-left hover:bg-accent/40 ${
                        activeDoc === doc.path ? "bg-accent/30 font-bold" : ""
                      }`}
                      onClick={() => setActiveDoc(doc.path)}
                    >
                      {doc.path}
                      {doc.tier && (
                        <span className="ml-2 font-semibold text-emerald-600">[{doc.tier}]</span>
                      )}
                      {doc.source && (
                        <span className="ml-1 text-xs text-gray-400">({doc.source})</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="col-span-5">
            <h2 className="mb-2 font-semibold">{activeDoc || "Select a document"}</h2>
            <div className="h-[400px] whitespace-pre-wrap rounded-md border bg-background p-4 text-sm overflow-auto">
              {content ? (
                <div className="prose prose-neutral dark:prose-invert max-w-none">
                  <SafeMarkdown>{content}</SafeMarkdown>
                </div>
              ) : (
                "Select a document to view its content."
              )}
            </div>
          </div>
        </div>
      )}

      {tab === "search" && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-6">
          <div className="col-span-1 space-y-4">
            <form className="mb-2 flex gap-2" onSubmit={doSearch}>
              <input
                className="w-full rounded border px-2 py-1"
                placeholder="Search docs/knowledge base…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Button type="submit" size="sm" disabled={searchLoading}>
                {searchLoading ? "…" : "Search"}
              </Button>
            </form>
            <ul className="max-h-72 space-y-1 overflow-y-auto text-xs">
              {hits.map((hit, i) => (
                <li key={`${hit.file ?? "snippet"}-${i}`}>
                  <button
                    className={`w-full rounded px-2 py-1 text-left hover:bg-accent/30 ${
                      selectedHit === i ? "bg-accent/40 font-bold" : ""
                    }`}
                    onClick={() => setSelectedHit(i)}
                  >
                    {hit.file || "Semantic Snippet"}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="col-span-5">
            {selectedHit !== null && hits[selectedHit] ? (
              <div>
                <div className="mb-2 font-bold">
                  {hits[selectedHit].file || "Semantic Snippet"}
                </div>
                <div className="max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded bg-gray-100 p-3 text-xs">
                  <div className="prose prose-neutral dark:prose-invert max-w-none">
                    <SafeMarkdown>{hits[selectedHit].snippet}</SafeMarkdown>
                  </div>
                </div>
                <div className="mt-2 text-xs text-gray-500">
                  Score: {typeof hits[selectedHit].score === "number"
                    ? hits[selectedHit].score.toFixed(2)
                    : "N/A"}{" "}
                  | Type: {hits[selectedHit].type || "?"}
                </div>
              </div>
            ) : (
              <div className="pt-10 text-center text-gray-500">
                {searchLoading ? "Searching…" : "Select a semantic hit to preview context."}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "context" && (
        <div className="mx-auto mt-4 max-w-3xl space-y-3">
          {/* Controls */}
          <form className="grid grid-cols-1 gap-2 md:grid-cols-5" onSubmit={fetchContextForPrompt}>
            <label className="md:col-span-3 flex flex-col text-sm">
              <span className="mb-1 font-medium">Ask about this doc</span>
              <input
                className="rounded border bg-background px-3 py-2"
                placeholder="e.g., Summarize the key actions and risks"
                value={ctxQuestion}
                onChange={(e) => setCtxQuestion(e.target.value)}
                disabled={ctxLoading}
                name="ask-query"
                id="ask-query"
                aria-label="Ask about this document"
              />
            </label>

            <label className="flex flex-col text-sm">
              <span className="mb-1 font-medium">Role</span>
              <select
                className="rounded border bg-background px-2 py-2"
                value={ctxRole}
                onChange={(e) => setCtxRole(e.target.value as Role)}
                disabled={ctxLoading}
                aria-label="Agent role"
              >
                <option value="docs">docs</option>
                <option value="planner">planner</option>
                <option value="codex">codex</option>
                <option value="control">control</option>
              </select>
            </label>

            <div className="flex items-end">
              <Button type="submit" className="w-full" disabled={ctxLoading || !ctxQuestion.trim()}>
                {ctxLoading ? "Asking…" : "Ask"}
              </Button>
            </div>
          </form>

          {/* Error */}
          {ctxError && (
            <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
              <div className="font-medium">Request error</div>
              <div className="mt-1 break-words font-mono">{ctxError}</div>
            </div>
          )}

          {/* Answer preview */}
          <div className="rounded-xl border bg-card p-4">
            <div className="mb-2 text-xs text-muted-foreground">Answer (final_text)</div>
            <div className="prose prose-neutral dark:prose-invert max-w-none">
              <SafeMarkdown>{ctxAnswer}</SafeMarkdown>
            </div>
            {ctxMetaItems.length > 0 && <MetaBadges items={ctxMetaItems} />}
          </div>

          {/* Context (debug) */}
          {!!ctxContext && (
            <div className="rounded-xl border bg-card/60 p-4">
              <button
                type="button"
                onClick={() => setCtxShow((v) => !v)}
                className="text-xs underline underline-offset-2"
                aria-expanded={ctxShow}
                aria-controls="agent-context"
              >
                {ctxShow ? "Hide injected context" : "Show injected context"}
              </button>
              {ctxShow && (
                <div
                  id="agent-context"
                  className="prose prose-sm prose-neutral dark:prose-invert mt-2 max-w-none"
                >
                  <SafeMarkdown>{ctxContext}</SafeMarkdown>
                </div>
              )}
            </div>
          )}

          {/* Active doc hint */}
          <div className="text-xs text-muted-foreground">
            Active doc:&nbsp;
            <span className="font-mono">{activeDoc ?? "— none selected —"}</span>
          </div>
        </div>
      )}
    </div>
  );
}
