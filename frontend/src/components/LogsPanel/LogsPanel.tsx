// File: LogsPanel.tsx
// Directory: frontend/src/components
// Purpose: Displays the system action log with results, file paths, timestamps, auto-refresh, action-type filtering, text-based search, and JSON/CSV download

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface LogEntry {
  id: string;
  timestamp: string;
  type: string;
  path?: string;
  status: string;
  result?: Record<string, unknown>;
}

export default function LogsPanel() {
  const [log, setLog] = useState<LogEntry[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filterType, setFilterType] = useState<string>("");
  const [searchText, setSearchText] = useState<string>("");

  async function fetchLog() {
    const res = await fetch("https://relay.wildfireranch.us/control/list_log", {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      }
    });
    const data = await res.json();
    setLog(data.log || []);
  }

  function downloadJSON() {
    const blob = new Blob([JSON.stringify(filteredLog, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "relay_log.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadCSV() {
    const headers = ["id", "timestamp", "type", "path", "status"];
    const csvRows = [headers.join(",")];
    filteredLog.forEach(entry => {
      const row = [
        entry.id,
        entry.timestamp,
        entry.type,
        entry.path || "",
        entry.status
      ].map(field => `"${field.replace(/"/g, '""')}"`);
      csvRows.push(row.join(","));
    });
    const csvContent = csvRows.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "relay_log.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => {
    fetchLog();
    if (!autoRefresh) return;
    const interval = setInterval(fetchLog, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const uniqueTypes = Array.from(new Set(log.map(l => l.type))).sort();
  const filteredLog = log.filter(entry => {
    const matchType = !filterType || entry.type === filterType;
    const matchSearch = !searchText || JSON.stringify(entry).toLowerCase().includes(searchText.toLowerCase());
    return matchType && matchSearch;
  });

  if (!filteredLog.length) return <p className="text-muted-foreground">No log entries{filterType ? ` of type '${filterType}'` : ""} found.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 mb-4 items-center">
        <Button variant={autoRefresh ? "default" : "outline"} onClick={() => setAutoRefresh(!autoRefresh)}>
          {autoRefresh ? "Auto-Refresh ON" : "Auto-Refresh OFF"}
        </Button>
        <div className="text-sm text-gray-500">Log updates every 15s</div>

        <select
          className="border rounded px-2 py-1 text-sm"
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
        >
          <option value="">All Types</option>
          {uniqueTypes.map(type => (
            <option key={type} value={type}>{type}</option>
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

      {filteredLog.map((entry) => (
        <Card key={entry.id}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">
              #{entry.id.slice(0, 8)} • {entry.timestamp}
            </div>
            <div className="text-sm">
              <strong>Type:</strong> {entry.type}
              {entry.path && (
                <span className="ml-2"><strong>Path:</strong> {entry.path}</span>
              )}
              <span className="ml-2"><strong>Status:</strong> {entry.status}</span>
            </div>
            <pre className="bg-muted p-2 rounded text-sm overflow-auto whitespace-pre-wrap">
              {JSON.stringify(entry.result, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
