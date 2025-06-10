// File: components/StatusPanel.tsx
// Directory: frontend/src/components
// Purpose: Display Relay service status and embed a UI panel for Google Docs sync and KB refresh

"use client"

import { useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import DocsSyncPanel from "@/components/DocsSyncPanel"
import { API_ROOT } from "@/lib/api" // ✅ Centralized import

// Type definitions for status summary response
interface StatusSummary {
  version?: { git_commit?: string }
  paths?: {
    base_path?: string
    resolved_paths?: Record<string, boolean>
  }
}

export default function StatusPanel() {
  const [status, setStatus] = useState<StatusSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    async function fetchStatus() {
      if (!API_ROOT) {
        setError("API URL not configured.")
        setLoading(false)
        return
      }
      try {
        const res = await fetch(`${API_ROOT}/status/summary`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: StatusSummary = await res.json()
        setStatus(data)
      } catch (err) {
        console.error("Status fetch error:", err)
        setError("Failed to load status.")
      } finally {
        setLoading(false)
      }
    }
    fetchStatus()
  }, [])

  if (loading) return <p className="text-sm text-muted-foreground">Loading service status…</p>
  if (error) return <p className="text-sm text-red-500">{error}</p>
  if (!status) return <p className="text-sm">No status data available.</p>

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

      {/* Embed DocsSyncPanel below status */}
      <div className="mt-6">
        <DocsSyncPanel />
      </div>
    </>
  )
}
