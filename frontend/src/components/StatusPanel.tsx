// File: components/StatusPanel.tsx
"use client"

import { useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"

// === Define a type-safe interface for the status response ===
type StatusSummary = {
  version?: { git_commit?: string }
  paths?: {
    base_path?: string
    resolved_paths?: Record<string, boolean>
  }
}

export default function StatusPanel() {
  const [status, setStatus] = useState<StatusSummary | null>(null)

  // === Fetch backend /status/summary on load ===
  useEffect(() => {
    fetch("https://relay.wildfireranch.us/status/summary")
      .then(res => res.json())
      .then(data => setStatus(data))
  }, [])

  if (!status) return <p>Loading status...</p>

  return (
    <Card className="mt-6">
      <CardContent className="p-4 space-y-2">
        <h2 className="text-xl font-bold">📊 Relay Status</h2>
        <div>
          <strong>Version:</strong> {status.version?.git_commit || "unknown"}
        </div>
        <div>
          <strong>Base Path:</strong> {status.paths?.base_path}
        </div>
        <div>
          <strong>Docs Folder Visibility:</strong>
          <ul className="list-disc ml-6">
            {Object.entries(status.paths?.resolved_paths || {}).map(([key, value]) => (
              <li key={key}>{key}: {value ? "✅" : "❌"}</li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  )
}
