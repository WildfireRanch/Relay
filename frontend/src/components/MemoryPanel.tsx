// File: MemoryPanel.tsx
// Directory: frontend/src/components
// Purpose: Displays per-user session memory with table/card toggle, filtering, drilldown, and context inspection

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";

interface MemoryEntry {
  timestamp: string;
  user: string;
  query: string;
  topics?: string[];
  files?: string[];
  summary?: string;
  context_length?: number;
  used_global_context?: boolean;
  context_files?: string[];
  agent_response?: string;
  prompt_length?: number;
  response_length?: number;
  fallback?: boolean;
}

type ViewMode = "cards" | "table";

export default function MemoryPanel() {
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [filterUser, setFilterUser] = useState("");
  const [filterGlobal, setFilterGlobal] = useState<"any" | "with" | "without">("any");
  const [fetchInfo, setFetchInfo] = useState<{ status: string; time: number; error?: string }>({
    status: "idle",
    time: 0
  });
  const [view, setView] = useState<ViewMode>("cards");
  const [modalContext, setModalContext] = useState<{ path: string; content: string } | null>(null);

  async function fetchMemory() {
    const start = Date.now();
    setFetchInfo({ status: "loading", time: 0 });
    try {
      const res = await fetch(`${API_ROOT}/logs/sessions/all`, {
        headers: {
          "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || ""
        }
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data = await res.json();
      setMemory(data.entries || []);
      setFetchInfo({ status: "success", time: Date.now() - start });
      console.debug("[MemoryPanel] Fetch complete:", {
        time: Date.now() - start,
        count: data.entries?.length,
        sample: data.entries?.[0]
      });
    } catch (e: unknown) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      setFetchInfo({ status: "error", time: Date.now() - start, error: errorMsg });
      setMemory([]);
      console.error("[MemoryPanel] Fetch failed:", e);
    }
  }

  // Fetch single context file content for drilldown modal
  async function fetchContextFile(path: string) {
    try {
      const res = await fetch(`${API_ROOT}/files/context?path=${encodeURIComponent(path)}`, {
        headers: {
          "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || ""
        }
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const content = await res.text();
      setModalContext({ path, content });
    } catch (e) {
      setModalContext({ path, content: `Failed to fetch: ${e}` });
    }
  }

  useEffect(() => { fetchMemory(); }, []);

  // Filtering and context-aware insights
  const users = Array.from(new Set(memory.map(m => m.user))).sort();
  const filtered = memory.filter(entry => {
    const matchUser = !filterUser || entry.user === filterUser;
    const matchSearch = !search || JSON.stringify(entry).toLowerCase().includes(search.toLowerCase());
    const matchGlobal =
      filterGlobal === "any"
        ? true
        : filterGlobal === "with"
        ? !!entry.used_global_context
        : !entry.used_global_context;
    return matchUser && matchSearch && matchGlobal;
  });

  // Insight summary
  const summary = {
    total: memory.length,
    filtered: filtered.length,
    users: users.length,
    avgContext: Math.round(filtered.reduce((a, m) => a + (m.context_length || 0), 0) / (filtered.length || 1)),
    usedGlobal: filtered.filter(m => m.used_global_context).length,
    fallback: filtered.filter(m => m.fallback).length
  };

  function downloadMemory() {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "session_memory.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  function replayQuery(query: string) {
    window.open(`/ask?question=${encodeURIComponent(query)}`, "_blank");
  }


  return (
    <div className="space-y-4">
      {/* Insights bar: fetch status, counts, averages */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500 mb-2 items-center">
        <span>Fetch: <b>{fetchInfo.status}</b>{fetchInfo.time ? ` (${fetchInfo.time}ms)` : ""}</span>
        <span>Total: <b>{summary.total}</b></span>
        <span>Filtered: <b>{summary.filtered}</b></span>
        <span>Users: <b>{summary.users}</b></span>
        <span>Avg. Context: <b>{isNaN(summary.avgContext) ? "n/a" : summary.avgContext}</b> chars</span>
        <span>Used Global Context: <b>{summary.usedGlobal}</b></span>
        <span>Fallbacks: <b>{summary.fallback}</b></span>
        {fetchInfo.error && <span className="text-red-600">Error: {fetchInfo.error}</span>}
        <Button onClick={fetchMemory} variant="outline">Refresh</Button>
        <Button onClick={downloadMemory} variant="outline">Download JSON</Button>
        <Button onClick={() => setView(view === "cards" ? "table" : "cards")} variant="secondary">
          {view === "cards" ? "Table View" : "Card View"}
        </Button>
      </div>
      {/* Filter/search controls */}
      <div className="flex gap-2 items-center mb-4">
        <select
          className="border rounded px-2 py-1 text-sm"
          value={filterUser}
          onChange={e => setFilterUser(e.target.value)}
        >
          <option value="">All Users</option>
          {users.map(u => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <select
          className="border rounded px-2 py-1 text-sm"
          value={filterGlobal}
          onChange={e => setFilterGlobal(e.target.value as "any" | "with" | "without")}
        >
          <option value="any">All Context</option>
          <option value="with">With Global Context</option>
          <option value="without">Without Global Context</option>
        </select>
        <input
          type="text"
          className="border rounded px-2 py-1 text-sm w-64"
          placeholder="Search memory..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>
      {/* Filtered/total counts */}
      <div className="text-xs text-gray-400 mb-2">
        Showing {filtered.length} of {memory.length} entries
        {search && <> | Search: <code>{search}</code></>}
        {filterUser && <> | User: <code>{filterUser}</code></>}
        {filterGlobal !== "any" && <> | Global Context: <code>{filterGlobal}</code></>}
      </div>
      {fetchInfo.status === "loading" ? (
        <div className="p-8 text-gray-400 animate-pulse">
          Loading memory logs...
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-sm text-muted-foreground p-4">No memory entries found for current filter.</div>
      ) : view === "table" ? (
        <div className="overflow-x-auto">
          <table className="min-w-full border text-xs">
            <thead>
              <tr className="bg-gray-100">
                <th className="px-2 py-1 text-left">Timestamp</th>
                <th className="px-2 py-1 text-left">User</th>
                <th className="px-2 py-1 text-left">Query</th>
                <th className="px-2 py-1 text-left">Topics</th>
                <th className="px-2 py-1 text-left">Context Files</th>
                <th className="px-2 py-1 text-left">Used Global</th>
                <th className="px-2 py-1 text-left">Fallback</th>
                <th className="px-2 py-1 text-left">Replay</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m, i) => (
                <tr key={i} className="border-t hover:bg-gray-50">
                  <td className="px-2 py-1">{new Date(m.timestamp).toLocaleString()}</td>
                  <td className="px-2 py-1">{m.user}</td>
                  <td className="px-2 py-1">{m.query}</td>
                  <td className="px-2 py-1">{Array.isArray(m.topics) && m.topics.join(", ")}</td>
                  <td className="px-2 py-1">
                    {(m.context_files ?? []).map((cf, idx) => (
                      <span key={cf}>
                        <a
                          className="underline cursor-pointer"
                          onClick={() => fetchContextFile(cf)}
                        >
                          {cf}
                        </a>
                        {idx < (m.context_files?.length ?? 0) - 1 ? ", " : ""}
                      </span>
                    ))}
                  </td>
                  <td className="px-2 py-1">
                    {m.used_global_context && (
                      <span className="inline-block px-2 py-1 text-xs bg-green-100 text-green-700 rounded">Yes</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    {m.fallback && (
                      <span className="inline-block px-2 py-1 text-xs bg-orange-100 text-orange-700 rounded">Fallback</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => replayQuery(m.query)}
                    >
                      🔁
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        filtered.map((m, i) => (
          <Card key={i}>
            <CardContent className="p-4 space-y-2">
              <div className="text-sm font-mono text-muted-foreground">
                {new Date(m.timestamp).toLocaleString()} • {m.user}
              </div>
              <div className="text-sm">
                <strong>Query:</strong> {m.query}
              </div>
              {Array.isArray(m.topics) && m.topics.length > 0 && (
                <div className="text-xs">Topics: {m.topics.join(", ")}</div>
              )}
              {Array.isArray(m.files) && m.files.length > 0 && (
                <div className="text-xs">Files: {m.files.join(", ")}</div>
              )}
              {(m.context_files ?? []).length > 0 && (
                <div className="text-xs text-blue-800">
                  <strong>Context Files:</strong>{" "}
                  {(m.context_files ?? []).map((cf, idx) => (
                    <span key={cf}>
                      <a
                        className="underline cursor-pointer"
                        onClick={() => fetchContextFile(cf)}
                      >
                        {cf}
                      </a>
                      {idx < (m.context_files?.length ?? 0) - 1 ? ", " : ""}
                    </span>
                  ))}
                </div>
              )}
              {typeof m.context_length === "number" && (
                <div className="text-xs text-gray-600">Context Length: {m.context_length} chars</div>
              )}
              {typeof m.prompt_length === "number" && (
                <div className="text-xs text-gray-600">Prompt Length: {m.prompt_length} | Response: {m.response_length}</div>
              )}
              {m.used_global_context && (
                <span className="inline-block px-2 py-1 text-xs bg-green-100 text-green-700 rounded">Global context</span>
              )}
              {m.fallback && (
                <span className="inline-block px-2 py-1 text-xs bg-orange-100 text-orange-700 rounded">Fallback</span>
              )}
              {m.summary && (
                <pre className="bg-muted p-2 rounded text-xs whitespace-pre-wrap">{m.summary}</pre>
              )}
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-blue-700">Debug: Raw Entry</summary>
                <pre className="bg-gray-100 p-2 rounded text-xs overflow-auto">{JSON.stringify(m, null, 2)}</pre>
              </details>
              <div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-2"
                  onClick={() => replayQuery(m.query)}
                >
                  🔁 Replay Query
                </Button>
              </div>
            </CardContent>
          </Card>
        ))
      )}

      {/* Context File Drilldown Modal */}
      {modalContext && (
        <div className="fixed inset-0 flex items-center justify-center z-50 bg-black bg-opacity-40">
          <div className="bg-white rounded shadow-lg max-w-2xl w-full p-6 relative">
            <div className="text-sm mb-2 font-bold">Context File: <code>{modalContext.path}</code></div>
            <pre className="bg-gray-100 p-4 rounded max-h-[400px] overflow-auto text-xs">{modalContext.content}</pre>
            <Button variant="secondary" onClick={() => setModalContext(null)} className="absolute top-2 right-2">
              Close
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
