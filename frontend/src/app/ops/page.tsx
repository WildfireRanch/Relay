"use client";

/**
 * =====================================================================
 * FILE: frontend/src/app/ops/page.tsx
 * NAME: Relay Ops Dashboard (Operator Runbook UI)
 * PURPOSE:
 *   Run health, ASK/MCP, KB/embeddings, and GitHub integration tests
 *   from the browser, with status/latency and streaming display.
 *
 * SECURITY MODEL:
 *   All requests go through the server proxy at /api/ops/* which:
 *     - injects ADMIN_API_KEY as x-api-key when missing
 *     - preserves streaming bodies (SSE/chunked)
 *     - normalizes host/origin to backend (avoids CORS/key leaks)
 *
 * ENV:
 *   NEXT_PUBLIC_API_URL : Backend base (e.g., https://relay.wildfireranch.us)
 *   ADMIN_API_KEY       : Server-only; injected by /api/ops proxy if present
 *
 * HOUSE STYLE:
 *   Clear file header, section headers, concise comments.
 * =====================================================================
 */

import React, { useMemo, useState } from "react";

/* ---------------------------------------------------------------------
 * SECTION: Types
 * -------------------------------------------------------------------*/
type HttpMethod = "GET" | "POST";
type TestSpec = {
  id: string;
  label: string;                 // Card title
  method: HttpMethod;
  path: string;                  // Backend path, e.g. "mcp/ping" (no leading slash)
  body?: unknown;                // JSON body for POST
  stream?: boolean;              // If true, show live chunked output
  requiresApiKey?: boolean;      // For operator hinting (proxy injects on server)
};

type TestResult = {
  id: string;
  ok: boolean;
  status: number | null;
  ms: number | null;
  startedAt: string;
  error?: string;
  json?: any;
  text?: string;                 // Non-JSON/stream text
};

/* ---------------------------------------------------------------------
 * SECTION: Test Catalog — keep in sync with backend routes
 * -------------------------------------------------------------------*/
const GROUPS: { title: string; items: TestSpec[] }[] = [
  {
    title: "Health",
    items: [
      { id: "livez",  label: "GET /livez",  method: "GET",  path: "livez" },
      { id: "readyz", label: "GET /readyz", method: "GET",  path: "readyz" },
    ],
  },
  {
    title: "ASK / Streaming",
    items: [
      { id: "ask_post",         label: "POST /ask",              method: "POST", path: "ask",            body: { question: "What is Relay?" } },
      { id: "ask_stream",       label: "POST /ask/stream",       method: "POST", path: "ask/stream",     body: { question: "Stream hello" }, stream: true },
      { id: "ask_codex_stream", label: "POST /ask/codex_stream", method: "POST", path: "ask/codex_stream", body: { question: "Code stream hello" }, stream: true },
    ],
  },
  {
    title: "MCP — Diagnostics & Run",
    items: [
      { id: "mcp_ping",     label: "GET /mcp/ping",                               method: "GET",  path: "mcp/ping" },
      { id: "mcp_diag",     label: "GET /mcp/diag",                               method: "GET",  path: "mcp/diag" },
      { id: "mcp_diag_ctx", label: "GET /mcp/diag_ctx?q=Relay%20Command%20Center", method: "GET",  path: "mcp/diag_ctx?q=Relay%20Command%20Center" },
      { id: "mcp_run",      label: "POST /mcp/run",                               method: "POST", path: "mcp/run", body: { query: "ping" } },
    ],
  },
  {
    title: "Status & Debug",
    items: [
      { id: "status_paths",   label: "GET /status/paths",   method: "GET", path: "status/paths" },
      { id: "status_env",     label: "GET /status/env",     method: "GET", path: "status/env" },
      { id: "status_version", label: "GET /status/version", method: "GET", path: "status/version" },
      { id: "status_summary", label: "GET /status/summary", method: "GET", path: "status/summary" },
      { id: "status_context", label: "GET /status/context", method: "GET", path: "status/context" },
      { id: "debug_env",      label: "GET /debug/env",      method: "GET", path: "debug/env" },
    ],
  },
  {
    title: "GitHub Integration",
    items: [
      { id: "gh_health",               label: "GET /gh/health",                         method: "GET", path: "gh/health" },
      { id: "gh_repos",                label: "GET /gh/repos",                          method: "GET", path: "gh/repos" },
      { id: "gh_integrations_ping",    label: "GET /integrations/github/ping",          method: "GET", path: "integrations/github/ping" },
      { id: "gh_integrations_diag",    label: "GET /integrations/github/diag",          method: "GET", path: "integrations/github/diag" },
      { id: "gh_integrations_app",     label: "GET /integrations/github/app",           method: "GET", path: "integrations/github/app" },
      { id: "gh_integrations_status",  label: "GET /integrations/github/status?branch=main", method: "GET", path: "integrations/github/status?branch=main" },
      { id: "gh_integrations_tree",    label: "GET /integrations/github/tree?ref=HEAD&recursive=true", method: "GET", path: "integrations/github/tree?ref=HEAD&recursive=true" },
      { id: "gh_integrations_contents",label: "GET /integrations/github/contents?path=&ref=main&raw=false", method: "GET", path: "integrations/github/contents?path=&ref=main&raw=false" },
    ],
  },
  {
    title: "KB / Embeddings / Ops",
    items: [
      { id: "kb_summary",   label: "GET /kb/summary",               method: "GET",  path: "kb/summary", requiresApiKey: true },
      { id: "kb_search_get",label: "GET /kb/search?query=Relay&k=5",method: "GET",  path: "kb/search?query=Relay&k=5" },
      { id: "kb_search_post",label:"POST /kb/search",               method: "POST", path: "kb/search", body: { query: "Relay", k: 5 } },
      { id: "kb_reindex",   label: "POST /kb/reindex (X-API-Key)",  method: "POST", path: "kb/reindex", requiresApiKey: true },
      { id: "emb_ping",     label: "GET /embeddings/ping",          method: "GET",  path: "embeddings/ping" },
      { id: "emb_status",   label: "GET /embeddings/status",        method: "GET",  path: "embeddings/status" },
      { id: "emb_rebuild",  label: "POST /embeddings/rebuild",      method: "POST", path: "embeddings/rebuild" },
    ],
  },
];

/* ---------------------------------------------------------------------
 * SECTION: Small helpers
 * -------------------------------------------------------------------*/
const cls = (...xs: (string | false | undefined)[]) => xs.filter(Boolean).join(" ");

const ErrorDisplay: React.FC<{ error?: string }> = ({ error }) => {
  if (!error) return null;
  return (
    <pre className="whitespace-pre-wrap text-red-700">
      {error}
    </pre>
  );
};


/* ---------------------------------------------------------------------
 * SECTION: Component
 * -------------------------------------------------------------------*/
export default function OpsPage() {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Record<string, TestResult>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(["livez", "readyz", "mcp_ping", "ask_post"].map((id) => [id, true]))
  );

  const all = useMemo(() => GROUPS.flatMap((g) => g.items), []);

  // Run a single test via server proxy (/api/ops/*); preserve streams
  async function runOne(spec: TestSpec) {
    const startedAt = new Date().toISOString();
    const t0 = Date.now();
    const url = `/api/ops/${spec.path}`;
    try {
      const resp = await fetch(url, {
        method: spec.method,
        headers: { "content-type": "application/json" },
        body: spec.method === "POST" ? JSON.stringify(spec.body ?? {}) : undefined,
      });

      // Streaming endpoints: append chunks to text
      if (spec.stream && resp.body) {
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let acc = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          acc += dec.decode(value, { stream: true });
          setResults((r) => ({
            ...r,
            [spec.id]: {
              id: spec.id,
              ok: resp.ok,
              status: resp.status,
              ms: Date.now() - t0,
              text: acc,
              startedAt,
            },
          }));
        }
        return;
      }

      const ct = resp.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const json = await resp.json();
        setResults((r) => ({
          ...r,
          [spec.id]: {
            id: spec.id,
            ok: resp.ok,
            status: resp.status,
            ms: Date.now() - t0,
            json,
            startedAt,
          },
        }));
      } else {
        const text = await resp.text();
        setResults((r) => ({
          ...r,
          [spec.id]: {
            id: spec.id,
            ok: resp.ok,
            status: resp.status,
            ms: Date.now() - t0,
            text,
            startedAt,
          },
        }));
      }
    } catch (e: any) {
      setResults((r) => ({
        ...r,
        [spec.id]: {
          id: spec.id,
          ok: false,
          status: null,
          ms: Date.now() - t0,
          error: e?.message || String(e),
          startedAt,
        },
      }));
    }
  }

  // Safer sequential run for long-ops/locks
  async function runSelected() {
    setRunning(true);
    const list = all.filter((t) => selected[t.id]);
    for (const spec of list) {
      // eslint-disable-next-line no-await-in-loop
      await runOne(spec);
    }
    setRunning(false);
  }

  function toggleGroup(title: string, on: boolean) {
    const group = GROUPS.find((g) => g.title === title)!;
    setSelected((prev) => ({
      ...prev,
      ...Object.fromEntries(group.items.map((i) => [i.id, on])),
    }));
  }

  /* -------------------------------------------------------------------
   * SECTION: Render
   * -----------------------------------------------------------------*/
  return (
    <div className="min-h-screen p-6 md:p-10 space-y-6">
      {/* Header & Controls */}
      <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Relay Ops Dashboard</h1>
          <p className="text-sm opacity-70">
            Run health, ASK/MCP, KB, and GitHub checks through a secure server proxy.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            className={cls("px-4 py-2 rounded-2xl shadow", running ? "opacity-60" : "bg-black text-white")}
            disabled={running}
            onClick={runSelected}
          >
            Run Selected
          </button>
          <button
            className="px-4 py-2 rounded-2xl shadow bg-white border"
            disabled={running}
            onClick={() => setResults({})}
          >
            Clear
          </button>
        </div>
      </header>

      {/* Groups */}
      {GROUPS.map((group) => (
        <section key={group.title} className="border rounded-2xl p-4 md:p-5 bg-white">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">{group.title}</h2>
            <div className="flex gap-2">
              <button className="text-xs underline" onClick={() => toggleGroup(group.title, true)}>
                Select
              </button>
              <button className="text-xs underline" onClick={() => toggleGroup(group.title, false)}>
                Unselect
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {group.items.map((spec) => {
              const res = results[spec.id];
              const isSel = !!selected[spec.id];
              return (
                <div
                  key={spec.id}
                  className={cls("rounded-2xl border p-3", isSel ? "ring-1 ring-black" : "opacity-70")}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">{spec.label}</div>
                      <div className="text-xs opacity-70">
                        {spec.method} · /{spec.path}
                      </div>
                      {spec.requiresApiKey && (
                        <div className="text-[11px] mt-1 text-amber-700">
                          Requires server ADMIN_API_KEY
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isSel}
                        onChange={(e) =>
                          setSelected((p) => ({ ...p, [spec.id]: e.target.checked }))
                        }
                        aria-label={`select ${spec.id}`}
                      />
                      <button
                        className="text-xs rounded-full px-3 py-1 border"
                        disabled={running}
                        onClick={() => runOne(spec)}
                      >
                        Run
                      </button>
                    </div>
                  </div>

                  {res ? (
                    <div className="mt-2 rounded-xl bg-gray-50 p-2 text-xs space-y-1">
                      <div className="flex gap-3 flex-wrap">
                        <span className={`px-2 py-0.5 rounded-full ${res.ok ? "bg-green-100" : "bg-red-100"}`}>
                          {res.ok ? "OK" : "FAIL"}
                        </span>
                        <span>Status: {res.status ?? "—"}</span>
                        <span>Latency: {res.ms ?? "—"} ms</span>
                        <span>Start: {res.startedAt.replace("T", " ").replace("Z", " UTC")}</span>
                      </div>

                      {/* error text */}
                      <ErrorDisplay error={res.error} />

                      {/* JSON payload */}
                      {res.json && (
                        <details className="bg-white rounded-lg p-2">
                          <summary className="cursor-pointer">JSON</summary>
                          <pre className="overflow-auto max-h-64">
                            {JSON.stringify(res.json, null, 2)}
                          </pre>
                        </details>
                      )}

                      {/* Text/stream payload */}
                      {res.text && !res.json && (
                        <details className="bg-white rounded-lg p-2">
                          <summary className="cursor-pointer">Body</summary>
                          <pre className="overflow-auto max-h-64 whitespace-pre-wrap">
                            {res.text}
                          </pre>
                        </details>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {/* Footer */}
      <footer className="text-xs opacity-60">
        Relay Ops Dashboard • v1 • {new Date().toISOString().slice(0, 10)}
      </footer>
    </div>
  );
}
