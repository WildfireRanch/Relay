// File: components/StatusPanel.tsx
// Directory: frontend/src/components
// Purpose: Display Relay service status and embed a UI panel for Google Docs sync and KB/context awareness

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import DocsSyncPanel from "@/components/DocsSyncPanel";
import { API_ROOT } from "@/lib/api";

interface StatusSummary {
  version?: { git_commit?: string };
  paths?: {
    base_path?: string;
    resolved_paths?: Record<string, boolean>;
  };
}

interface ContextStatus {
  context_files: string[];
  global_context_used: string;
  global_context_manual_last_updated: string;
  global_context_auto_last_updated: string;
}

export default function StatusPanel() {
  const [status, setStatus] = useState<StatusSummary | null>(null);
  const [context, setContext] = useState<ContextStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    async function fetchStatus() {
      if (!API_ROOT) {
        setError("API URL not configured.");
        setLoading(false);
        return;
      }
      try {
        const [statusRes, contextRes] = await Promise.all([
          fetch(`${API_ROOT}/status/summary`),
          fetch(`${API_ROOT}/status/context`),
        ]);
        if (!statusRes.ok || !contextRes.ok)
          throw new Error("Failed to fetch one or more endpoints");
        const statusData: StatusSummary = await statusRes.json();
        const contextData: ContextStatus = await contextRes.json();
        setStatus(statusData);
        setContext(contextData);
      } catch (err) {
        console.error("Status fetch error:", err);
        setError("Failed to load status.");
      } finally {
        setLoading(false);
      }
    }
    fetchStatus();
  }, []);

  if (loading) return <p className="text-sm text-muted-foreground">Loading service status…</p>;
  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!status) return <p className="text-sm">No status data available.</p>;

  return (
    <>
      <Card className="mt-6">
        <CardContent className="p-4 space-y-3">
          <h2 className="text-xl font-bold">📊 Relay Service Status</h2>
          <div><strong>Version:</strong> {status.version?.git_commit || "unknown"}</div>
          <div><strong>Base Path:</strong> {status.paths?.base_path || "—"}</div>
          <div>
            <strong>Docs Folder Health:</strong>
            <ul className="list-disc ml-6">
              {Object.entries(status.paths?.resolved_paths || {}).map(
                ([pathKey, ok]) => (
                  <li key={pathKey} className="text-sm">
                    {pathKey}: {ok ? "✅ OK" : "❌ Missing"}
                  </li>
                )
              )}
            </ul>
          </div>
        </CardContent>
      </Card>

      {context && (
        <Card className="mt-6">
          <CardContent className="p-4 space-y-3">
            <h2 className="text-xl font-bold">🧠 Context Awareness</h2>
            <div><strong>Context Strategy:</strong> {context.global_context_used === "manual" ? "📝 Manual" : context.global_context_used === "auto" ? "🤖 Auto-generated" : "None"}</div>
            <div><strong>Last Manual Update:</strong> {context.global_context_manual_last_updated}</div>
            <div><strong>Last Auto Update:</strong> {context.global_context_auto_last_updated}</div>
            <div>
              <strong>Active Context Files:</strong>
              <ul className="list-disc ml-6">
                {context.context_files.map((file) => (
                  <li key={file} className="text-sm">{file}</li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Embed DocsSyncPanel below status */}
      <div className="mt-6">
        <DocsSyncPanel />
      </div>
    </>
  );
}
