// File: frontend/src/components/LogsPanel.tsx
// Purpose: Full-featured system log/audit/error viewer with filtering, searching, stack trace viewing, and CSV/JSON export.
// Compatible with robust backend logger (fields: time, source, level, message, stack_trace, etc).

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";
import SafeMarkdown from "@/components/SafeMarkdown";

interface AuditLogEntry {
  id: string;
  time: string;
  source: string;
  level: string;
  message: string;
  stack_trace?: string;
  [key: string]: any;
}

export default function AuditPanel() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [searchText, setSearchText] = useState<string>("");

  async function fetchLogs() {
    const params = new URLSearchParams();
    if (levelFilter) params.append("level_filter", levelFilter);
    params.append("n", "100");
    const res = await fetch(`${API_ROOT}/logs/recent?${params.toString()}`, {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || ""
      }
    });
    const data = await res.json();
    const mapped = (data.logs || []).map((entry: any, idx: number) => ({
      id: entry.id || entry.time || `${idx}`,
      time: entry.time || "",
      source: entry.source || "system",
      level: entry.level || "INFO",
      message: entry.message || "",
      stack_trace: entry.stack_trace || "",
      ...entry,
    }));
    setLogs(mapped);
  }

  useEffect(() => {
    fetchLogs();
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, levelFilter]);

  const uniqueSources = Array.from(new Set(logs.map(l => l.source))).sort();

  const filteredLogs = logs.filter(entry => {
    const matchLevel = !levelFilter || entry.level === levelFilter;
    const matchSource = !sourceFilter || entry.source === sourceFilter;
    const matchSearch = !searchText || (
      JSON.stringify(entry).toLowerCase().includes(searchText.toLowerCase())
    );
    return matchLevel && matchSource && matchSearch;
  });

  function downloadJSON() {
    const blob = new Blob([JSON.stringify(filteredLogs, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "audit_log.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadCSV() {
    const headers = ["time", "source", "level", "message"];
    const csvRows = [headers.join(",")];
    filteredLogs.forEach(entry => {
      const row = [
        entry.time,
        entry.source,
        entry.level,
        (entry.message || "").replace(/"/g, '""').replace(/\n/g, "\\n")
      ].map(field => `"${String(field)}"`);
      csvRows.push(row.join(","));
    });
    const csvContent = csvRows.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "audit_log.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!filteredLogs.length)
    return (
      <p className="text-muted-foreground">
        No log entries{levelFilter ? ` of level '${levelFilter}'` : ""}{sourceFilter ? ` from '${sourceFilter}'` : ""} found.
      </p>
    );

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-4 items-center">
        <Button variant={autoRefresh ? "default" : "outline"} onClick={() => setAutoRefresh(!autoRefresh)}>
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
            <option key={source} value={source}>{source}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search logs..."
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          className="border rounded px-2 py-1 text-sm w-60"
        />
        <Button onClick={downloadJSON} variant="secondary">
          Download JSON
        </Button>
        <Button onClick={downloadCSV} variant="outline">
          Export CSV
        </Button>
      </div>

      {/* Log entries */}
      {filteredLogs.map((entry) => (
        <Card key={entry.id} className={entry.level === "ERROR" ? "border-red-400" : ""}>
          <CardContent className="p-4 space-y-2">
            <div className="text-xs font-mono text-muted-foreground">
              {entry.time} • <span className="font-bold">{entry.source}</span> [{entry.level}]
            </div>
            <div className="text-sm break-words">
              <SafeMarkdown>{entry.message}</SafeMarkdown>
            </div>
            {entry.stack_trace && entry.stack_trace.trim() && (
              <details>
                <summary className="text-red-700 cursor-pointer">Stack trace</summary>
                <pre className="bg-red-100 text-xs p-2 rounded overflow-x-auto">{entry.stack_trace}</pre>
              </details>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
