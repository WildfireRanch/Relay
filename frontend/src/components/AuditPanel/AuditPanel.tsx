// File: AuditPanel.tsx
// Directory: frontend/src/components
// Purpose: Unified agent audit dashboard with drilldown into agent actions/patches and related context

"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

// === Types ===
type LogEntry = {
  id: string;
  type?: string;
  path?: string;
  timestamp: string;
  status: string;
  user?: string;
  comment?: string;
  result?: unknown;
};
type ActionDetail = {
  id: string;
  action: {
    context?: string;
    rationale?: string;
    diff?: string;
  };
  history?: {
    timestamp: string;
    status: string;
    user?: string;
    comment?: string;
  }[];
};

export default function AuditPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<{ user?: string; type?: string; status?: string }>({});
  const [search, setSearch] = useState("");
  const [exporting, setExporting] = useState(false);
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const [relatedAction, setRelatedAction] = useState<ActionDetail | null>(null);

  // === Fetch audit logs from backend ===
  async function fetchLog() {
    try {
      const res = await fetch("/control/list_log", {
        headers: { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" }
      });
      if (!res.ok) throw new Error("Bad response");
      const data = await res.json();
      setLogs(data.log || []);
    } catch (err) {
      setLogs([]);
    }
  }

  // === Fetch related queue action by id ===
  async function fetchRelated(id: string) {
    try {
      const res = await fetch("/control/list_queue", {
        headers: { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" }
      });
      if (!res.ok) throw new Error("Bad response");
      const data = await res.json();
      const action: ActionDetail | undefined = (data.actions as ActionDetail[] | undefined)?.find(a => a.id === id);
      setRelatedAction(action || null);
    } catch (err) {
      setRelatedAction(null);
    }
  }

  useEffect(() => {
    fetchLog();
    const interval = setInterval(fetchLog, 15000);
    return () => clearInterval(interval);
  }, []);

  // === Filtered/search results ===
  const filtered = logs.filter(entry =>
    (!filter.user || entry.user === filter.user) &&
    (!filter.type || entry.type === filter.type) &&
    (!filter.status || entry.status === filter.status) &&
    (search.trim() === "" ||
      (entry.comment?.toLowerCase().includes(search.toLowerCase()) ?? false) ||
      (entry.type?.toLowerCase().includes(search.toLowerCase()) ?? false) ||
      (entry.path?.toLowerCase().includes(search.toLowerCase()) ?? false) ||
      (entry.id?.toLowerCase().includes(search.toLowerCase()) ?? false))
  );

  // === Export as JSON/CSV ===
  function exportLog(format: "json" | "csv") {
    setExporting(true);
    let blob;
    if (format === "json") {
      blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    } else {
      const header = ["id", "type", "path", "timestamp", "status", "user", "comment"];
      const csv = [
        header.join(","),
        ...filtered.map(l => header.map(k => `"${(l as Record<string, string | undefined>)[k] ?? ""}"`).join(","))
      ].join("\n");
      blob = new Blob([csv], { type: "text/csv" });
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `relay_audit_log.${format}`;
    a.click();
    setTimeout(() => {
      setExporting(false);
      URL.revokeObjectURL(url);
    }, 1000);
  }

  // === UI ===
  return (
    <div className="max-w-5xl mx-auto py-8">
      <h2 className="font-bold text-xl mb-6">🛡️ Audit Log & Operator Panel</h2>
      <div className="flex gap-2 mb-4 items-end">
        <input
          placeholder="🔎 Search user/type/path/comment/ID"
          className="border rounded px-2 py-1 w-60 text-sm"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <input
          placeholder="Filter user"
          className="border rounded px-2 py-1 text-xs"
          value={filter.user || ""}
          onChange={e => setFilter(f => ({ ...f, user: e.target.value }))}
        />
        <input
          placeholder="Filter type"
          className="border rounded px-2 py-1 text-xs"
          value={filter.type || ""}
          onChange={e => setFilter(f => ({ ...f, type: e.target.value }))}
        />
        <select
          className="border rounded px-2 py-1 text-xs"
          value={filter.status || ""}
          onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
        >
          <option value="">Status</option>
          <option value="approved">approved</option>
          <option value="denied">denied</option>
          <option value="executed">executed</option>
          <option value="pending">pending</option>
        </select>
        <Button onClick={() => fetchLog()} className="ml-2">Refresh</Button>
        <Button
          variant="outline"
          disabled={exporting}
          onClick={() => exportLog("json")}
        >
          Export JSON
        </Button>
        <Button
          variant="outline"
          disabled={exporting}
          onClick={() => exportLog("csv")}
        >
          Export CSV
        </Button>
      </div>
      <div className="bg-gray-100 rounded-md p-2 max-h-[60vh] overflow-auto text-xs">
        {filtered.length === 0 && (
          <div className="text-muted-foreground text-center py-8">
            No log entries match the filters.
          </div>
        )}
        <table className="w-full">
          <thead>
            <tr className="font-semibold text-gray-700 bg-gray-200">
              <th className="px-2 py-1 text-left">Time</th>
              <th className="px-2 py-1 text-left">Status</th>
              <th className="px-2 py-1 text-left">User</th>
              <th className="px-2 py-1 text-left">Type</th>
              <th className="px-2 py-1 text-left">Path</th>
              <th className="px-2 py-1 text-left">ID</th>
              <th className="px-2 py-1 text-left">Comment</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((entry, i) => (
              <tr
                key={i}
                className="border-t border-gray-300 cursor-pointer hover:bg-blue-50"
                onClick={() => { setSelected(entry); fetchRelated(entry.id); }}
              >
                <td className="px-2 py-1">{entry.timestamp}</td>
                <td className="px-2 py-1">
                  <Badge variant={
                    entry.status === "approved" ? "success" :
                    entry.status === "denied" ? "destructive" :
                    entry.status === "pending" ? "secondary" : "default"
                  }>
                    {entry.status}
                  </Badge>
                </td>
                <td className="px-2 py-1">{entry.user || ""}</td>
                <td className="px-2 py-1">{entry.type || ""}</td>
                <td className="px-2 py-1 font-mono">{entry.path || ""}</td>
                <td className="px-2 py-1 font-mono">{entry.id.slice(0, 8)}</td>
                <td className="px-2 py-1">{entry.comment || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-gray-400 mt-3">
        Tip: Click any row for full drilldown: context, rationale, diff, timeline, and more.
      </div>

      {/* === Per-action Modal Drilldown === */}
      {selected && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/30 z-50">
          <div className="bg-white p-6 rounded shadow-lg w-full max-w-xl relative">
            <button className="absolute top-2 right-3 text-xl" onClick={() => { setSelected(null); setRelatedAction(null); }}>&times;</button>
            <h3 className="font-bold mb-2">Action Detail (#{selected.id.slice(0, 8)})</h3>
            <div className="mb-2 text-xs">
              <strong>Status:</strong>{" "}
              <Badge variant={
                selected.status === "approved" ? "success" :
                selected.status === "denied" ? "destructive" : "secondary"
              }>
                {selected.status}
              </Badge><br />
              <strong>User:</strong> {selected.user}<br />
              <strong>Type:</strong> {selected.type}<br />
              <strong>Path:</strong> {selected.path}<br />
              <strong>Comment:</strong> {selected.comment}<br />
              <strong>Timestamp:</strong> {selected.timestamp}
            </div>
            {relatedAction?.action?.context && (
              <details>
                <summary className="cursor-pointer text-blue-700 mb-2">View Agent Context</summary>
                <pre className="bg-gray-50 p-2 rounded text-xs max-h-40 overflow-auto whitespace-pre-wrap">{relatedAction.action.context}</pre>
              </details>
            )}
            {relatedAction?.action?.rationale && (
              <div className="text-xs italic mb-2"><strong>Agent rationale:</strong> {relatedAction.action.rationale}</div>
            )}
            {relatedAction?.action?.diff && (
              <details>
                <summary className="cursor-pointer text-blue-700 mb-2">View Diff</summary>
                <pre className="bg-yellow-50 p-2 rounded text-xs max-h-40 overflow-auto whitespace-pre-wrap">{relatedAction.action.diff}</pre>
              </details>
            )}
            {relatedAction?.history && (
              <div>
                <h4 className="font-semibold mt-2 mb-1 text-sm">Timeline</h4>
                <ul className="bg-gray-100 p-2 rounded text-xs max-h-32 overflow-auto border">
                  {relatedAction.history.map((h, i) => (
                    <li key={i}><span className="font-mono">{h.timestamp}</span> • <Badge>{h.status}</Badge> {h.user && <span className="ml-2 text-blue-700">{h.user}</span>} {h.comment && <span className="ml-2 italic">{h.comment}</span>}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
