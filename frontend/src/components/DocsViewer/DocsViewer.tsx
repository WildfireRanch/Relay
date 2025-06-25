// File: frontend/src/components/DocsViewer.tsx
// Purpose: Browse, manage, and debug semantic context docs with tier-aware metadata, sync, and promote/prune support

"use client";

import { API_ROOT } from "@/lib/api";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const apiUrl = API_ROOT || "";

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

export default function DocsViewer() {
  const [tab, setTab] = useState<"docs" | "search" | "context">("docs");

  const [docs, setDocs] = useState<KBMeta[]>([]);
  const [activeDoc, setActiveDoc] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");

  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [hits, setHits] = useState<KBHit[]>([]);
  const [selectedHit, setSelectedHit] = useState<number | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const [ctxQuestion, setCtxQuestion] = useState("");
  const [ctxLoading, setCtxLoading] = useState(false);
  const [ctxResult, setCtxResult] = useState<string>("");

  useEffect(() => {
    if (tab === "docs") loadDocs();
  }, [tab]);

  useEffect(() => {
    if (activeDoc) loadContent(activeDoc);
    else setContent("");
  }, [activeDoc]);

  async function loadDocs() {
    try {
      const res = await fetch(`${apiUrl}/docs/list`);
      const data = await res.json();
      setDocs(data.files || []);
    } catch {
      setDocs([]);
    }
  }

  async function loadContent(path: string) {
    try {
      const res = await fetch(`${apiUrl}/docs/view?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      setContent(data.content || "");
    } catch {
      setContent("Failed to load doc.");
    }
  }

  async function handleSync() {
    setSyncing(true);
    setSyncStatus(null);
    try {
      const res = await fetch(`${apiUrl}/docs/sync`, { method: "POST" });
      const data = await res.json();
      setSyncStatus(`✅ Synced ${data.synced_docs.length} docs.`);
      await loadDocs();
    } catch {
      setSyncStatus("❌ Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function handlePrune() {
    try {
      const res = await fetch(`${apiUrl}/docs/prune_duplicates`, { method: "POST" });
      const data = await res.json();
      alert(`🧹 Pruned ${data.removed || 0} duplicates.`);
      await loadDocs();
    } catch {
      alert("❌ Prune failed.");
    }
  }

  async function handlePromote(path: string) {
    try {
      const res = await fetch(`${apiUrl}/docs/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await res.json();
      alert(`⬆️ Promoted to canonical: ${data.promoted || "unknown"}`);
      await loadDocs();
    } catch {
      alert("❌ Promote failed.");
    }
  }

  async function doSearch(e?: React.FormEvent) {
    if (e) e.preventDefault();
    setSearchLoading(true);
    setHits([]);
    setSelectedHit(null);
    try {
      const res = await fetch(`${apiUrl}/kb/search?query=${encodeURIComponent(search)}`);
      const data = await res.json();
      setHits(data.results || []);
    } catch {
      setHits([]);
    }
    setSearchLoading(false);
  }

  async function fetchContextForPrompt(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!ctxQuestion) return;
    setCtxLoading(true);
    setCtxResult("");
    try {
      const res = await fetch(
        `${apiUrl}/ask?question=${encodeURIComponent(ctxQuestion)}&debug=true`
      );
      const data = await res.json();
      setCtxResult(data.context || "No context returned.");
    } catch {
      setCtxResult("Failed to fetch context window.");
    }
    setCtxLoading(false);
  }

  return (
    <div className="max-w-5xl mx-auto py-6">
      <div className="flex gap-4 mb-4">
        <Button variant={tab === "docs" ? "default" : "outline"} onClick={() => setTab("docs")}>
          📝 Docs
        </Button>
        <Button variant={tab === "search" ? "default" : "outline"} onClick={() => setTab("search")}>
          🔍 Semantic Search
        </Button>
        <Button variant={tab === "context" ? "default" : "outline"} onClick={() => setTab("context")}>
          🧠 Agent Context
        </Button>
      </div>

      {tab === "docs" && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="space-y-4 col-span-1">
            <div className="space-y-2">
              <h2 className="font-semibold">Docs</h2>
              <div className="h-[400px] overflow-auto border rounded-md p-2 text-xs">
                {docs.map((doc) => (
                  <div key={doc.path} className="mb-2">
                    <Button
                      variant={doc.path === activeDoc ? "default" : "ghost"}
                      className="w-full justify-start text-left"
                      onClick={() => setActiveDoc(doc.path)}
                    >
                      {doc.path.replace(/^.*[\\/]/, "")}
                    </Button>
                    <div className="text-gray-500">
                      {doc.tier || "—"} · {doc.source || "local"}
                    </div>
                    <div className="text-gray-400">{doc.doc_id || "—"}</div>
                    {doc.path !== activeDoc && (
                      <div className="flex gap-1 mt-1">
                        <Button variant="outline" size="xs" onClick={() => handlePromote(doc.path)}>
                          ⬆️ Promote
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <Button onClick={handleSync} disabled={syncing} className="w-full text-sm">
              {syncing ? "🔄 Syncing..." : "🔄 Sync Google Docs"}
            </Button>
            <Button onClick={handlePrune} className="w-full text-sm mt-2">
              🧹 Prune Duplicates
            </Button>
            {syncStatus && <p className="text-xs text-muted-foreground mt-2">{syncStatus}</p>}
          </div>
          <div className="col-span-3">
            <h2 className="font-semibold mb-2">{activeDoc || "Select a document"}</h2>
            <div className="h-[400px] overflow-auto border rounded-md p-4 whitespace-pre-wrap text-sm">
              {content || "Select a document to view its content."}
            </div>
          </div>
        </div>
      )}

      {tab === "search" && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="space-y-4 col-span-1">
            <form className="flex gap-2 mb-2" onSubmit={doSearch}>
              <input
                className="border px-2 py-1 rounded w-full"
                placeholder="Semantic search code/docs…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Button className="px-3" type="submit" disabled={searchLoading}>
                {searchLoading ? "…" : "Go"}
              </Button>
            </form>
            <div className="h-[400px] overflow-auto border rounded-md p-2">
              {hits.map((hit, i) => (
                <Button
                  key={i}
                  variant={selectedHit === i ? "default" : "ghost"}
                  className="w-full justify-start text-left text-xs"
                  onClick={() => setSelectedHit(i)}
                >
                  {(hit.file || hit.type || "snippet") + (hit.line ? ` :L${hit.line}` : "")}
                  <div className="truncate">{hit.snippet.slice(0, 70)}…</div>
                  <span className="text-gray-500">
                    {hit.score !== undefined ? `score: ${hit.score.toFixed(2)}` : ""}
                  </span>
                </Button>
              ))}
            </div>
          </div>
          <div className="col-span-3">
            {selectedHit !== null && hits[selectedHit] ? (
              <div>
                <div className="font-bold mb-2">{hits[selectedHit].file || "Semantic Snippet"}</div>
                <pre className="bg-gray-100 p-3 rounded max-h-[70vh] overflow-y-auto whitespace-pre-wrap text-xs">
                  {hits[selectedHit].snippet}
                </pre>
                <div className="text-xs text-gray-500 mt-2">
                  Score: {hits[selectedHit].score?.toFixed(2) || "N/A"} | Type:{" "}
                  {hits[selectedHit].type || "?"}
                </div>
              </div>
            ) : (
              <div className="text-gray-500 text-center pt-10">
                {searchLoading ? "Searching…" : "Select a semantic hit to preview context."}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "context" && (
        <div className="max-w-2xl mx-auto mt-8">
          <form className="flex gap-2 mb-4" onSubmit={fetchContextForPrompt}>
            <input
              className="border px-2 py-1 rounded w-full"
              placeholder="Type a user/agent prompt…"
              value={ctxQuestion}
              onChange={(e) => setCtxQuestion(e.target.value)}
            />
            <Button type="submit" disabled={ctxLoading}>
              {ctxLoading ? "…" : "Show Context"}
            </Button>
          </form>
          <div className="h-[400px] overflow-auto border rounded-md p-4 whitespace-pre-wrap text-xs bg-gray-50">
            {ctxLoading
              ? "Fetching context…"
              : ctxResult
                ? ctxResult
                : "Enter a prompt to see what context the agent would use."}
          </div>
        </div>
      )}
    </div>
  );
}
