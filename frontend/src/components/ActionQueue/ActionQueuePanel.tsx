// File: ActionQueuePanel.tsx
// Directory: frontend/src/components
// Purpose: Superpanel for agent patch/action queue with approve/deny, context diff, and deep audit

"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { API_ROOT } from "@/lib/api";

type ActionStatus = "pending" | "approved" | "denied";

type HistoryEntry = {
  timestamp: string;
  status: ActionStatus;
  user?: string;
  comment?: string;
};

type Action = {
  id: string;
  timestamp: string;
  status: ActionStatus;
  action: {
    type: string;
    path?: string;
    content?: string;
    diff?: string;
    context?: string;
    rationale?: string;
  };
  history?: HistoryEntry[];
};

export default function ActionQueuePanel() {
  const [actions, setActions] = useState<Action[]>([]);
  const [processing, setProcessing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [showContext, setShowContext] = useState<{ [id: string]: boolean }>({});
  const [showHistory, setShowHistory] = useState<{ [id: string]: boolean }>({});
  const [comment, setComment] = useState<{ [id: string]: string }>({});
  const [compareContextId, setCompareContextId] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";
  const USER_ID = "bret";

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_ROOT}/control/list_queue`, {
        headers: {
          "X-API-Key": API_KEY,
          "X-User-Id": USER_ID
        }
      });
      if (!res.ok) throw new Error("Bad response");
      const data = await res.json();
      setActions(data.actions || []);
    } catch (err) {
      console.error("Queue fetch failed", err);
      setError("Failed to fetch action queue.");
    }
    setLoading(false);
  }, [API_KEY, USER_ID]);

  const updateStatus = async (id: string, action: "approve" | "deny") => {
    setProcessing(id + action);
    try {
      const res = await fetch(`${API_ROOT}/control/${action}_action`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": API_KEY,
          "X-User-Id": USER_ID
        },
        body: JSON.stringify({ id, comment: comment[id] || "" })
      });
      if (!res.ok) throw new Error(`${action} failed`);
      await fetchQueue();
      setComment((prev) => ({ ...prev, [id]: "" }));
    } catch (err) {
      console.error(`Action ${action} failed`, err);
      setError(`Failed to ${action} action.`);
    }
    setProcessing(null);
  };

  useEffect(() => {
    fetchQueue();
    if (!autoRefresh) return;
    const interval = setInterval(fetchQueue, 15000);
    return () => clearInterval(interval);
  }, [fetchQueue, autoRefresh]);

  const getActionById = (id: string) => actions.find(a => a.id === id);

  if (error) return <p className="text-red-500">{error}</p>;
  if (loading) return <p className="text-muted-foreground">Loading queue...</p>;
  if (!actions.length) return <p className="text-muted-foreground">No actions in queue.</p>;

  return (
    <div className="space-y-4">
      <div className="flex gap-2 mb-4 items-center">
        <Button variant={autoRefresh ? "default" : "outline"} onClick={() => setAutoRefresh(!autoRefresh)}>
          {autoRefresh ? "Auto-Refresh ON" : "Auto-Refresh OFF"}
        </Button>
        <span className="text-xs text-gray-400">Queue updates every 15s</span>
      </div>
      {actions.map((a) => (
        <Card key={a.id}>
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center gap-2 text-sm font-mono text-muted-foreground">
              #{a.id.slice(0, 8)} • {a.timestamp}
              <Badge variant={
                a.status === "approved" ? "success" :
                a.status === "denied" ? "destructive" : "secondary"
              }>
                {a.status}
              </Badge>
            </div>

            <div className="text-sm">
              <strong>Type:</strong> {a.action.type}
              {a.action.path && <span className="ml-2"><strong>Path:</strong> {a.action.path}</span>}
            </div>

            {a.action.rationale && (
              <div className="text-xs text-blue-800 mt-1 italic">
                <strong>Why?</strong> {a.action.rationale}
              </div>
            )}

            {a.action.diff ? (
              <details>
                <summary className="cursor-pointer text-xs text-blue-700">View Diff</summary>
                <pre className="bg-muted p-2 rounded text-xs overflow-auto whitespace-pre-wrap">
                  {a.action.diff}
                </pre>
              </details>
            ) : (
              <pre className="bg-muted p-2 rounded text-sm overflow-auto whitespace-pre-wrap">
                {a.action.content?.slice(0, 500) || "No content"}
              </pre>
            )}

            {a.action.context && (
              <Button
                size="sm"
                variant="outline"
                className="my-2"
                onClick={() => setShowContext(prev => ({ ...prev, [a.id]: !prev[a.id] }))}
              >
                {showContext[a.id] ? "Hide Agent Context" : "Show Agent Context"}
              </Button>
            )}

            {showContext[a.id] && a.action.context && (
              <pre className="bg-gray-100 p-2 rounded text-xs max-h-32 overflow-auto mt-2">
                {a.action.context}
              </pre>
            )}

            {/* Context diff compare */}
            <div className="mt-2">
              <label className="text-xs mr-2">Compare context to:</label>
              <select
                className="border rounded px-1 py-0.5 text-xs"
                value={compareContextId === a.id ? "" : compareContextId || ""}
                onChange={e => setCompareContextId(e.target.value || null)}
              >
                <option value="">Select previous action…</option>
                {actions.filter(other => other.id !== a.id && other.action.context).map(other => (
                  <option key={other.id} value={other.id}>
                    #{other.id.slice(0, 8)} {other.action.type}
                  </option>
                ))}
              </select>
              {compareContextId && getActionById(compareContextId) && a.action.context && (
                <details>
                  <summary className="cursor-pointer text-xs text-blue-700 mt-1">Show Context Diff</summary>
                  <pre className="bg-yellow-100 p-2 rounded text-xs overflow-auto whitespace-pre-wrap">
                    {diffContext(a.action.context, getActionById(compareContextId)?.action.context || "")}
                  </pre>
                </details>
              )}
            </div>

            <Button
              size="sm"
              variant="ghost"
              className="my-2"
              onClick={() => setShowHistory(prev => ({ ...prev, [a.id]: !prev[a.id] }))}
            >
              {showHistory[a.id] ? "Hide History" : "Show History"}
            </Button>

            {showHistory[a.id] && Array.isArray(a.history) && (
              <ul className="bg-gray-50 p-2 rounded text-xs mt-1 max-h-32 overflow-auto border">
                {a.history.map((h, i) => (
                  <li key={i}>
                    <span className="font-mono">{h.timestamp}</span> • <Badge>{h.status}</Badge>
                    {h.user && <span className="ml-2 text-blue-700">{h.user}</span>}
                    {h.comment && <span className="ml-2 italic">{h.comment}</span>}
                  </li>
                ))}
              </ul>
            )}

            {a.status === "pending" && (
              <form className="flex flex-col gap-2 mt-2" onSubmit={e => e.preventDefault()}>
                <Textarea
                  id={`comment-${a.id}`}
                  name={`comment-${a.id}`}
                  placeholder="Optional comment (why approve/deny?)"
                  value={comment[a.id] || ""}
                  onChange={e =>
                    setComment(prev => ({ ...prev, [a.id]: e.target.value }))
                  }
                  className="text-xs"
                  rows={2}
                />
                <div className="flex gap-2">
                  <Button
                    variant="default"
                    onClick={() => updateStatus(a.id, "approve")}
                    disabled={processing === a.id + "approve"}
                    type="button"
                  >
                    {processing === a.id + "approve" ? "Approving..." : "Approve"}
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => updateStatus(a.id, "deny")}
                    disabled={processing === a.id + "deny"}
                    type="button"
                  >
                    {processing === a.id + "deny" ? "Denying..." : "Deny"}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );

  // Simple line diff for context comparison
  function diffContext(ctx1: string, ctx2: string): string {
    const lines1 = new Set((ctx1 || "").split("\n"));
    const lines2 = new Set((ctx2 || "").split("\n"));
    let out = "";
    for (const l of lines1) {
      if (!lines2.has(l)) out += `+ ${l}\n`;
    }
    for (const l of lines2) {
      if (!lines1.has(l)) out += `- ${l}\n`;
    }
    return out || "No differences.";
  }
}
