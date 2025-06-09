// File: components/DocsSyncPanel.tsx
// Directory: frontend/src/components
// Purpose: UI panel to trigger Google Docs sync and KB refresh, managing API feedback and file lists

"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"

export default function DocsSyncPanel() {
  // Base API URL from environment
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  if (!apiUrl) {
    console.error("NEXT_PUBLIC_API_URL is not defined")
  }

  // Component state
  const [status, setStatus] = useState<string | null>(null)
  const [files, setFiles] = useState<string[]>([])
  const [loading, setLoading] = useState<boolean>(false)

  /**
   * Trigger a sync operation at the given endpoint and handle results.
   * @param endpoint 'sync', 'refresh_kb', or 'full_sync'
   */
  const triggerSync = async (endpoint: string) => {
    if (!apiUrl) {
      setStatus("❌ API URL not configured")
      return
    }
    // Reset and set loading state
    setStatus("⏳ Running...")
    setFiles([])
    setLoading(true)
    try {
      const res = await fetch(`${apiUrl}/docs/${endpoint}`, { method: "POST" })
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status}`)
      }
      const data = await res.json()
      // Handle response
      if (Array.isArray(data.synced_docs)) {
        setFiles(data.synced_docs)
        setStatus(`✅ Synced ${data.synced_docs.length} docs.`)
      } else if (data.message) {
        setStatus(`✅ ${data.message}`)
      } else {
        setStatus('✅ Operation completed.')
      }
    } catch (err) {
      console.error("DocsSync error:", err)
      setStatus("❌ Failed to sync. See console for details.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">🧠 Sync & Refresh Docs</h2>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => triggerSync("sync")} disabled={loading}>
          {loading ? '⏳ Syncing...' : '🔄 Sync Google Docs'}
        </Button>
        <Button onClick={() => triggerSync("refresh_kb")} disabled={loading}>
          {loading ? '⏳ Refreshing...' : '🧠 Refresh KB'}
        </Button>
        <Button onClick={() => triggerSync("full_sync")} disabled={loading}>
          {loading ? '⏳ Working...' : '🚀 Full Sync'}
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
    </div>
  )
}
