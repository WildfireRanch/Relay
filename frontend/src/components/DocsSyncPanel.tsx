// File: components/DocsSyncPanel.tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";

export default function DocsSyncPanel() {
  const [status, setStatus] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // New state for reindex button
  const [reindexStatus, setReindexStatus] = useState<string | null>(null);
  const [reindexLoading, setReindexLoading] = useState<boolean>(false);

  /**
   * Trigger a sync operation at the given endpoint and handle results.
   * @param endpoint 'sync', 'refresh_kb', or 'full_sync'
   */
  const triggerSync = async (endpoint: string) => {
    if (!API_ROOT) {
      setStatus("❌ API URL not configured");
      return;
    }
    setStatus("⏳ Running...");
    setFiles([]);
    setLoading(true);
    try {
      const res = await fetch(`${API_ROOT}/docs/${endpoint}`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status}`);
      }
      const data = await res.json();
      if (Array.isArray(data.synced_docs)) {
        setFiles(data.synced_docs);
        setStatus(`✅ Synced ${data.synced_docs.length} docs.`);
      } else if (data.message) {
        setStatus(`✅ ${data.message}`);
      } else {
        setStatus("✅ Operation completed.");
      }
    } catch (err) {
      console.error("DocsSync error:", err);
      setStatus("❌ Failed to sync. See console for details.");
    } finally {
      setLoading(false);
    }
  };

  // --- NEW: Trigger a KB reindex (admin only) ---
  const triggerReindex = async () => {
    if (!API_ROOT) {
      setReindexStatus("❌ API URL not configured");
      return;
    }
    setReindexStatus("⏳ Reindexing...");
    setReindexLoading(true);
    try {
      const res = await fetch(`${API_ROOT}/admin/trigger_reindex`, {
        method: "POST",
        headers: {
          // If you use a static admin API key for local, include it here
          // For production, secure this!
          "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "",
        },
      });
      const data = await res.json();
      if (res.ok) {
        setReindexStatus(`✅ ${data.message || "Reindex complete."}`);
      } else {
        setReindexStatus(`❌ ${data.detail || "Reindex failed."}`);
      }
    } catch (err) {
      console.error("Reindex error:", err);
      setReindexStatus("❌ Failed to reindex. See console for details.");
    } finally {
      setReindexLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">🧠 Sync & Refresh Docs</h2>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => triggerSync("sync")} disabled={loading}>
          {loading ? "⏳ Syncing..." : "🔄 Sync Google Docs"}
        </Button>
        <Button onClick={() => triggerSync("refresh_kb")} disabled={loading}>
          {loading ? "⏳ Refreshing..." : "🧠 Refresh KB"}
        </Button>
        <Button onClick={() => triggerSync("full_sync")} disabled={loading}>
          {loading ? "⏳ Working..." : "🚀 Full Sync"}
        </Button>
      </div>

      {status && <div className="mt-2 text-sm text-muted-foreground">{status}</div>}

      {files.length > 0 && (
        <ul className="mt-2 list-disc list-inside">
          {files.map((f) => (
            <li key={f} className="text-sm">{f}</li>
          ))}
        </ul>
      )}

      {/* Divider */}
      <hr className="my-4" />

      {/* Reindex Button */}
      <div>
        <h3 className="text-base font-medium mb-2">Admin: Reindex KB</h3>
        <Button
          onClick={triggerReindex}
          disabled={reindexLoading}
          variant="destructive"
          className="mb-2"
        >
          {reindexLoading ? "⏳ Reindexing..." : "🛠️ Reindex Now"}
        </Button>
        {reindexStatus && (
          <div className={`mt-1 text-sm ${reindexStatus.startsWith("✅") ? "text-green-600" : "text-red-500"}`}>
            {reindexStatus}
          </div>
        )}
      </div>
    </div>
  );
}
