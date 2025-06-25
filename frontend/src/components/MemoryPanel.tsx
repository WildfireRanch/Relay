// File: MemoryPanel.tsx
// Directory: frontend/src/components/
// Purpose : Displays per-user session memory with context injection source tracking,
//           filtering, drilldown, and debug display with tier-aware context summary

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";

interface ContextSource {
  type: string;
  title?: string;
  path?: string;
  tier?: string;
  score?: number;
  doc_id?: string;
}

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
  files_used?: ContextSource[];
  agent_response?: string;
  prompt_length?: number;
  response_length?: number;
  fallback?: boolean;
}

function isNonEmptyArray<T>(arr: T[] | undefined | null): arr is T[] {
  return Array.isArray(arr) && arr.length > 0;
}

export default function MemoryPanel() {
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [filterUser, setFilterUser] = useState("");
  const [filterGlobal, setFilterGlobal] = useState<"any" | "with" | "without">("any");
  const [fetchInfo, setFetchInfo] = useState<{ status: string; time: number; error?: string }>({
    status: "idle",
    time: 0
  });
  const [modalContext, setModalContext] = useState<{ path: string; content: string } | null>(null);

  useEffect(() => { fetchMemory(); }, []);

  async function fetchMemory() {
    const start = Date.now();
    setFetchInfo({ status: "loading", time: 0 });
    try {
      const res = await fetch(`${API_ROOT}/logs/sessions/all`, {
        headers: { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" }
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data = await res.json();
      setMemory(data.entries || []);
      setFetchInfo({ status: "success", time: Date.now() - start });
    } catch (e: unknown) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      setFetchInfo({ status: "error", time: Date.now() - start, error: errorMsg });
      setMemory([]);
    }
  }

  async function fetchContextFile(path: string) {
    try {
      const res = await fetch(`${API_ROOT}/files/context?path=${encodeURIComponent(path)}`, {
        headers: { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" }
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const content = await res.text();
      setModalContext({ path, content });
    } catch (e) {
      setModalContext({ path, content: `Failed to fetch: ${e}` });
    }
  }

  const users = Array.from(new Set(memory.map(m => m.user))).sort();
  const filtered = memory
    .filter((m: MemoryEntry) => {
      const matchUser = !filterUser || m.user === filterUser;
      const matchSearch = !search || JSON.stringify(m).toLowerCase().includes(search.toLowerCase());
      const matchGlobal = filterGlobal === "any" ? true : filterGlobal === "with" ? !!m.used_global_context : !m.used_global_context;
      return matchUser && matchSearch && matchGlobal;
    })
    .sort((a, b) => {
      const tierScore = (tier: string | undefined) => {
        switch (tier) {
          case "global": return 3;
          case "project": return 2;
          case "code": return 1;
          default: return 0;
        }
      };
      const maxTier = (files?: ContextSource[]) => Math.max(...(files || []).map(f => tierScore(f.tier)), 0);
      return maxTier(b.files_used) - maxTier(a.files_used);
    });

  function replayQuery(query: string) {
    window.open(`/ask?question=${encodeURIComponent(query)}`, "_blank");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-gray-500 mb-2 items-center">
        <span>Fetch: <b>{fetchInfo.status}</b>{fetchInfo.time ? ` (${fetchInfo.time}ms)` : ""}</span>
        <span>Total: <b>{memory.length}</b></span>
        <span>Filtered: <b>{filtered.length}</b></span>
        <span>Users: <b>{users.length}</b></span>
        <span>Global: <b>{filtered.filter(m => m.used_global_context).length}</b></span>
        <Button onClick={fetchMemory} variant="outline">Refresh</Button>
      </div>

      <div className="flex gap-2 mb-4">
        <select className="border rounded px-2 py-1 text-sm" value={filterUser} onChange={e => setFilterUser(e.target.value)}>
          <option value="">All Users</option>
          {users.map(u => <option key={u} value={u}>{u}</option>)}
        </select>
        <select className="border rounded px-2 py-1 text-sm" value={filterGlobal} onChange={e => setFilterGlobal(e.target.value as any)}>
          <option value="any">All Context</option>
          <option value="with">With Global</option>
          <option value="without">Without Global</option>
        </select>
        <input className="border rounded px-2 py-1 text-sm w-64" placeholder="Search memory..." value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {filtered.map((m: MemoryEntry, i: number) => (
        <Card key={i}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">{new Date(m.timestamp).toLocaleString()} • {m.user}</div>
            <div className="text-sm"><strong>Query:</strong> {m.query}</div>
            {isNonEmptyArray(m.topics) && <div className="text-xs">Topics: {m.topics.join(", ")}</div>}
            {isNonEmptyArray(m.files) && <div className="text-xs">Files: {m.files.join(", ")}</div>}

            {isNonEmptyArray(m.context_files) && (
              <div className="text-xs text-blue-800">
                <strong>Context Files:</strong>{" "}
                {m.context_files.map((cf, idx, arr) => (
                  <span key={cf}>
                    <a className="underline cursor-pointer" onClick={() => fetchContextFile(cf)}>{cf}</a>
                    {idx < arr.length - 1 ? ", " : ""}
                  </span>
                ))}
              </div>
            )}

            {isNonEmptyArray(m.files_used) && (
              <div className="text-xs text-purple-700">
                <strong>Injected:</strong>{" "}
                {m.files_used.map((f, idx, arr) => (
                  <span key={idx}>
                    <span className="underline cursor-pointer" onClick={() => f.path && fetchContextFile(f.path)}>
                      {f.path || f.title || f.doc_id || f.type}
                    </span>
                    {f.tier && <span className="ml-1 text-gray-500">[{f.tier}]</span>}
                    {idx < arr.length - 1 ? ", " : ""}
                  </span>
                ))}
              </div>
            )}

            <div className="text-xs text-gray-600">
              {typeof m.context_length === "number" && <>Context Length: {m.context_length} chars<br /></>}
              {typeof m.prompt_length === "number" && <>Prompt: {m.prompt_length}, Response: {m.response_length}</>}
            </div>

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

            <Button size="sm" variant="ghost" className="mt-2" onClick={() => replayQuery(m.query)}>🔁 Replay</Button>
          </CardContent>
        </Card>
      ))}

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