// File: MemoryPanel.tsx
// Directory: frontend/src/components
// Purpose: Displays per-user session memory from /logs/sessions with filtering and JSON export

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

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

export default function MemoryPanel() {
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [filterUser, setFilterUser] = useState("");
  const [filterGlobal, setFilterGlobal] = useState<"any" | "with" | "without">("any");
  const [fetchInfo, setFetchInfo] = useState<{ status: string; time: number; error?: string }>({ status: "idle", time: 0 });

  async function fetchMemory() {
    const start = Date.now();
    setFetchInfo({ status: "loading", time: 0 });
    try {
      const res = await fetch("https://relay.wildfireranch.us/logs/sessions/all", {
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
    } catch (e: any) {
      setFetchInfo({ status: "error", time: Date.now() - start, error: e?.message });
      setMemory([]);
      console.error("[MemoryPanel] Fetch failed:", e);
    }
  }

  useEffect(() => { fetchMemory(); }, []);

  // Advanced filtering
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

  // Insights
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
      {/* Debug/Insights bar */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500 mb-2 items-center">
        <span>Fetch: <b>{fetchInfo.status}</b>{fetchInfo.time ? ` (${fetchInfo.time}ms)` : ""}</span>
        <span>Total: <b>{summary.total}</b></span>
        <span>Filtered: <b>{summary.filtered}</b></span>
        <span>Users: <b>{summary.users}</b></span>
        <span>Avg. Context: <b>{isNaN(summary.avgContext) ? "n/a" : summary.avgContext}</b> chars</span>
        <span>Used Global Context: <b>{summary.usedGlobal}</b></span>
        <span>Fallbacks: <b>{summary.fallback}</b></span>
        {fetchInfo.error && <span className="text-red-600">Error: {fetchInfo.error}</span>}
      </div>
      <div className="flex gap-2 items-center mb-4">
        <select className="border rounded px-2 py-1 text-sm" value={filterUser} onChange={e => setFilterUser(e.target.value)}>
          <option value="">All Users</option>
          {users.map(u => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <select className="border rounded px-2 py-1 text-sm" value={filterGlobal} onChange={e => setFilterGlobal(e.target.value as any)}>
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
        <Button onClick={downloadMemory} variant="outline">Download JSON</Button>
      </div>
      <div className="text-xs text-gray-400 mb-2">
        Showing {filtered.length} of {memory.length} entries
        {search && <> | Search: <code>{search}</code></>}
        {filterUser && <> | User: <code>{filterUser}</code></>}
        {filterGlobal !== "any" && <> | Global Context: <code>{filterGlobal}</code></>}
      </div>
      {filtered.length === 0 && (
        <div className="text-sm text-muted-foreground p-4">No memory entries found for current filter.</div>
      )}

      {filtered.map((m, i) => (
        <Card key={i}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">
              {m.timestamp} • {m.user}
            </div>
            <div className="text-sm">
              <strong>Query:</strong> {m.query}
            </div>
            {m.topics?.length > 0 && (
              <div className="text-xs">Topics: {m.topics.join(", ")}</div>
            )}
            {m.files?.length > 0 && (
              <div className="text-xs">Files: {m.files.join(", ")}</div>
            )}
            {m.context_files?.length && (
              <div className="text-xs text-blue-800">
                <strong>Context Files:</strong> {m.context_files.join(", ")}
              </div>
            )}
            {typeof m.context_length === "number" && (
              <div className="text-xs text-gray-600">Context Length: {m.context_length} chars</div>
            )}
            {typeof m.prompt_length === "number" && (
              <div className="text-xs text-gray-600">Prompt Length: {m.prompt_length} | Response: {m.response_length}</div>
            )}
            {m.used_global_context && (
              <div className="text-xs text-green-700">Global context used ✅</div>
            )}
            {m.fallback && (
              <div className="text-xs text-orange-600">Fallback/no custom context ❗</div>
            )}
            {m.summary && (
              <pre className="bg-muted p-2 rounded text-xs whitespace-pre-wrap">{m.summary}</pre>
            )}
            {/* Debug: show raw entry as collapsible */}
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-blue-700">Debug: Raw Entry</summary>
              <pre className="bg-gray-100 p-2 rounded text-xs overflow-auto">{JSON.stringify(m, null, 2)}</pre>
            </details>
            {/* Replay/QC */}
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
      ))}
    </div>
  );
}
