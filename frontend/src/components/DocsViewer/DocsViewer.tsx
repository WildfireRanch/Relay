// File: frontend/src/components/DocsViewer.tsx
// Purpose: Browse, manage, and debug semantic context docs with tier-aware metadata.
//          Renders all doc/snippet/context output via SafeMarkdown for safety/uniformity.

"use client";

import { API_ROOT } from "@/lib/api";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import SafeMarkdown from "@/components/SafeMarkdown";

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

const apiUrl = API_ROOT || "";

// --- Main DocsViewer Component ---
export default function DocsViewer() {
  // UI State
  const [tab, setTab] = useState<"docs" | "search" | "context">("docs");
  const [docs, setDocs] = useState<KBMeta[]>([]);
  const [activeDoc, setActiveDoc] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");

  // Sync/Prune State
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);

  // Semantic Search State
  const [search, setSearch] = useState("");
  const [hits, setHits] = useState<KBHit[]>([]);
  const [selectedHit, setSelectedHit] = useState<number | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  // Context Tab State
  const [ctxQuestion, setCtxQuestion] = useState("");
  const [ctxLoading, setCtxLoading] = useState(false);
  const [ctxResult, setCtxResult] = useState<string>("");

  // --- Load docs when switching to docs tab ---
  useEffect(() => {
    if (tab === "docs") loadDocs();
  }, [tab]);

  // --- Load doc content when activeDoc changes ---
  useEffect(() => {
    if (activeDoc) loadContent(activeDoc);
    else setContent("");
  }, [activeDoc]);

  // --- Fetch: docs list ---
  async function loadDocs() {
    try {
      const res = await fetch(`${apiUrl}/docs/list`);
      const data = await res.json();
      setDocs(data.files || []);
    } catch {
      setDocs([]);
    }
  }

  // --- Fetch: doc content ---
  async function loadContent(path: string) {
    try {
      const res = await fetch(`${apiUrl}/docs/view?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      setContent(data.content || "");
    } catch {
      setContent("Failed to load doc.");
    }
  }

  // --- Sync, Prune, Promote, Pin, Set Tier actions ---
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
  async function handlePin(path: string) {
    try {
      const res = await fetch(`${apiUrl}/docs/mark_priority`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, pinned: true }),
      });
      const data = await res.json();
      alert(`📌 Pinned: ${data.updated}`);
      await loadDocs();
    } catch {
      alert("❌ Failed to pin doc.");
    }
  }
  async function handleSetTier(path: string, tier: string) {
    try {
      const res = await fetch(`${apiUrl}/docs/mark_priority`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, tier }),
      });
      const data = await res.json();
      alert(`🎯 Tier set to: ${data.tier}`);
      await loadDocs();
    } catch {
      alert("❌ Failed to set tier.");
    }
  }

  // --- Semantic Search ---
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

  // --- Agent Context Query ---
  async function fetchContextForPrompt(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!ctxQuestion) return;
    setCtxLoading(true);
    setCtxResult("");
    try {
      const res = await fetch(`${apiUrl}/ask?question=${encodeURIComponent(ctxQuestion)}&debug=true`);
      const data = await res.json();
      setCtxResult(data.context || "No context returned.");
    } catch {
      setCtxResult("Failed to fetch context window.");
    }
    setCtxLoading(false);
  }

  // --- UI ---
  return (
    <div className="max-w-5xl mx-auto py-6">
      {/* Tab Switcher */}
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

      {/* Docs Tab */}
      {tab === "docs" && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="space-y-4 col-span-1">
            {/* Document List & Controls */}
            <div>
              <div className="font-semibold mb-2">Knowledge Base Files</div>
              <ul className="space-y-1 text-xs max-h-80 overflow-y-auto">
                {docs.map((doc) => (
                  <li key={doc.path}>
                    <button
                      className={`w-full text-left py-1 px-2 rounded hover:bg-accent/40 ${
                        activeDoc === doc.path ? "bg-accent/30 font-bold" : ""
                      }`}
                      onClick={() => setActiveDoc(doc.path)}
                    >
                      {doc.path}
                      {doc.tier && (
                        <span className="ml-2 text-emerald-600 font-semibold">[{doc.tier}]</span>
                      )}
                      {doc.source && (
                        <span className="ml-1 text-xs text-gray-400">({doc.source})</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex gap-2 flex-wrap mt-3">
              <Button size="sm" onClick={handleSync} disabled={syncing}>
                {syncing ? "Syncing…" : "Sync"}
              </Button>
              <Button size="sm" variant="secondary" onClick={handlePrune}>Prune</Button>
              {activeDoc && (
                <>
                  <Button size="sm" variant="outline" onClick={() => handlePromote(activeDoc)}>Promote</Button>
                  <Button size="sm" variant="outline" onClick={() => handlePin(activeDoc)}>Pin</Button>
                  <Button size="sm" variant="outline" onClick={() => handleSetTier(activeDoc, "A")}>Tier A</Button>
                  <Button size="sm" variant="outline" onClick={() => handleSetTier(activeDoc, "B")}>Tier B</Button>
                </>
              )}
            </div>
            {syncStatus && <div className="text-xs mt-2">{syncStatus}</div>}
          </div>
          <div className="col-span-3">
            <h2 className="font-semibold mb-2">{activeDoc || "Select a document"}</h2>
            <div className="h-[400px] overflow-auto border rounded-md p-4 whitespace-pre-wrap text-sm bg-background">
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

      {/* Semantic Search Tab */}
      {tab === "search" && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="space-y-4 col-span-1">
            <form className="flex gap-2 mb-2" onSubmit={doSearch}>
              <input
                className="border px-2 py-1 rounded w-full"
                placeholder="Search docs/knowledge base…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Button type="submit" size="sm" disabled={searchLoading}>
                {searchLoading ? "…" : "Search"}
              </Button>
            </form>
            <ul className="space-y-1 text-xs max-h-72 overflow-y-auto">
              {hits.map((hit, i) => (
                <li key={i}>
                  <button
                    className={`w-full text-left py-1 px-2 rounded hover:bg-accent/30 ${
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
          <div className="col-span-3">
            {selectedHit !== null && hits[selectedHit] ? (
              <div>
                <div className="font-bold mb-2">{hits[selectedHit].file || "Semantic Snippet"}</div>
                <div className="bg-gray-100 p-3 rounded max-h-[70vh] overflow-y-auto whitespace-pre-wrap text-xs">
                  <div className="prose prose-neutral dark:prose-invert max-w-none">
                    <SafeMarkdown>{hits[selectedHit].snippet}</SafeMarkdown>
                  </div>
                </div>
                <div className="text-xs text-gray-500 mt-2">
                  Score: {hits[selectedHit].score?.toFixed(2) || "N/A"} | Type: {hits[selectedHit].type || "?"}
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

      {/* Agent Context Tab */}
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
                ? (
                    <div className="prose prose-neutral dark:prose-invert max-w-none">
                      <SafeMarkdown>{ctxResult}</SafeMarkdown>
                    </div>
                  )
                : "Enter a prompt to see what context the agent would use."}
          </div>
        </div>
      )}
    </div>
  );
}
