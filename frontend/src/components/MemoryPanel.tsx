// File: MemoryPanel.tsx
// Directory: frontend/src/components
// Purpose: Displays per-user session memory from /logs/sessions with filtering and JSON export

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface MemoryEntry {
  timestamp: string;
  user: string;
  query: string;
  topics?: string[];
  files?: string[];
  summary?: string;
}

export default function MemoryPanel() {
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [filterUser, setFilterUser] = useState("");

  async function fetchMemory() {
    const res = await fetch("https://relay.wildfireranch.us/logs/sessions/all", {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      }
    });
    const data = await res.json();
    setMemory(data.entries || []);
  }

  useEffect(() => {
    fetchMemory();
  }, []);

  const users = Array.from(new Set(memory.map(m => m.user))).sort();
  const filtered = memory.filter(entry => {
    const matchUser = !filterUser || entry.user === filterUser;
    const matchSearch = !search || JSON.stringify(entry).toLowerCase().includes(search.toLowerCase());
    return matchUser && matchSearch;
  });

  function downloadMemory() {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "session_memory.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center mb-4">
        <select
          className="border rounded px-2 py-1 text-sm"
          value={filterUser}
          onChange={e => setFilterUser(e.target.value)}
        >
          <option value="">All Users</option>
          {users.map(u => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <input
          type="text"
          className="border rounded px-2 py-1 text-sm w-64"
          placeholder="Search memory..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <Button onClick={downloadMemory} variant="outline">Download JSON</Button>
      </div>

      {filtered.map((m, i) => (
        <Card key={i}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">
              {m.timestamp} • {m.user}
            </div>
            <div className="text-sm">
              <strong>Query:</strong> {m.query}
            </div>
            {m.topics?.length && (
              <div className="text-xs">Topics: {m.topics.join(", ")}</div>
            )}
            {m.files?.length && (
              <div className="text-xs">Files: {m.files.join(", ")}</div>
            )}
            {m.summary && (
              <pre className="bg-muted p-2 rounded text-xs whitespace-pre-wrap">{m.summary}</pre>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
