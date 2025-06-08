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
  const [error, setError] = useState<string | null>(null)

  // === Fetch backend /status/summary on load ===
  useEffect(() => {
    const loadStatus = async () => {
      try {
        const res = await fetch("/api/status/summary")
        if (!res.ok) throw new Error(res.statusText)
        const data = await res.json()
        setStatus(data)
      } catch (err) {
        console.error("Failed to fetch status", err)
        setError("Failed to load status")
      }
    }
    loadStatus()
  }, [])

  if (error) return <p>{error}</p>
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
