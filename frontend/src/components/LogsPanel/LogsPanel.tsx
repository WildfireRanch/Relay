// File: frontend/src/components/LogsPanel/LogsPanel.tsx
// Purpose: Production-grade system log/audit/error viewer with filtering, searching, stack trace viewing, and CSV/JSON export.

"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";
import SafeMarkdown from "@/components/SafeMarkdown";

export interface AuditLogEntry {
  id: string;
  time: string;
  source: string;
  level: string;
  message: string;
  stack_trace?: string;
  [key: string]: unknown;
}

// === Utility Export Functions =================================================
function exportJSON(logs: AuditLogEntry[]) {
  const blob = new Blob([JSON.stringify(logs, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "logs_audit.json";
  link.click();
  URL.revokeObjectURL(url);
}

function exportCSV(logs: AuditLogEntry[]) {
  const headers = ["time", "source", "level", "message"];
  const csvRows = [headers.join(",")];

  logs.forEach(entry => {
    const row = [
      entry.time,
      entry.source,
      entry.level,
      (entry.message || "").toString().replace(/"/g, '""').replace(/\n/g, "\\n"),
    ].map(field => `"${field}"`);
    csvRows.push(row.join(","));
  });

  const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "logs_audit.csv";
  link.click();
  URL.revokeObjectURL(url);
}

// === Main Component ============================================================
export default function LogsPanel() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [searchText, setSearchText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setError(null);
      const params = new URLSearchParams();
      if (levelFilter) params.append("level_filter", levelFilter);
      params.append("n", "100");

      const res = await fetch(`${API_ROOT}/logs/recent?${params.toString()}`, {
        headers: {
          "X-API-Key": (process.env.NEXT_PUBLIC_API_KEY as string) || "",
        },
      });

      if (!res.ok) throw new Error(`Error fetching logs: ${res.status}`);

      const data = await res.json();

      const mapped: AuditLogEntry[] = Array.isArray(data.logs)
        ? data.logs.map((entry: Record<string, unknown>, idx: number) => ({
            id: String(entry.id || entry.time || idx),
            time: String(entry.time || ""),
            source: String(entry.source || "system"),
            level: String(entry.level || "INFO"),
            message: String(entry.message || ""),
            stack_trace: typeof entry.stack_trace === "string" ? entry.stack_trace : "",
            ...entry,
          }))
        : [];

      setLogs(mapped);
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error("Unknown error");
      setError(err.message);
    }
  }, [levelFilter]);

  useEffect(() => {
    fetchLogs();
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, levelFilter, fetchLogs]);

  const uniqueSources = Array.from(new Set(logs.map(log => log.source))).sort();

  const filteredLogs = logs.filter(entry => {
    const matchesLevel = !levelFilter || entry.level === levelFilter;
    const matchesSource = !sourceFilter || entry.source === sourceFilter;
    const matchesSearch =
      !searchText ||
      JSON.stringify(entry).toLowerCase().includes(searchText.toLowerCase());

    return matchesLevel && matchesSource && matchesSearch;
  });

  if (error) {
    return (
      <p className="text-red-600 font-mono p-4 bg-red-50 rounded">
        Failed to load logs: {error}
      </p>
    );
  }

  if (!filteredLogs.length) {
    return (
      <p className="text-muted-foreground">
        No log entries
        {levelFilter ? ` of level '${levelFilter}'` : ""}
        {sourceFilter ? ` from '${sourceFilter}'` : ""} found.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-4 items-center">
        <Button
          variant={autoRefresh ? "default" : "outline"}
          onClick={() => setAutoRefresh(!autoRefresh)}
        >
          {autoRefresh ? "Auto-Refresh ON" : "Auto-Refresh OFF"}
        </Button>
        <span className="text-sm text-gray-500">Log updates every 15s</span>

        <select
          className="border rounded px-2 py-1 text-sm"
          value={levelFilter}
          onChange={e => setLevelFilter(e.target.value)}
        >
          <option value="">All Levels</option>
          <option value="INFO">INFO</option>
          <option value="ERROR">ERROR</option>
          <option value="WARNING">WARNING</option>
        </select>

        <select
          className="border rounded px-2 py-1 text-sm"
          value={sourceFilter}
          onChange={e => setSourceFilter(e.target.value)}
        >
          <option value="">All Sources</option>
          {uniqueSources.map(source => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Search logs..."
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          className="border rounded px-2 py-1 text-sm w-60"
        />

        <Button onClick={() => exportJSON(filteredLogs)} variant="secondary">
          Download JSON
        </Button>
        <Button onClick={() => exportCSV(filteredLogs)} variant="outline">
          Export CSV
        </Button>
      </div>

      {/* Log Entries */}
      {filteredLogs.map(entry => (
        <Card key={entry.id} className={entry.level === "ERROR" ? "border-red-400" : ""}>
          <CardContent className="p-4 space-y-2">
            <div className="text-xs font-mono text-muted-foreground">
              {entry.time} • <span className="font-bold">{entry.source}</span> [{entry.level}]
            </div>
            <div className="text-sm break-words">
              <SafeMarkdown>{entry.message}</SafeMarkdown>
            </div>
            {entry.stack_trace && (
              <details>
                <summary className="text-red-700 cursor-pointer">Stack trace</summary>
                <pre className="bg-red-100 text-xs p-2 rounded overflow-x-auto whitespace-pre-wrap">
                  {entry.stack_trace}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
