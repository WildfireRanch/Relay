import { API_ROOT } from "@/lib/api";
// File: components/DocsViewer.tsx
// Directory: frontend/src/components/DocsViewer
// Purpose: List and view Markdown docs, with ability to trigger Google Docs sync

"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"

// Base API URL from environment
const apiUrl = API_ROOT || ""
if (process.env.NODE_ENV === 'development' && !apiUrl) {
  console.error("NEXT_PUBLIC_API_URL is not defined")
}

export default function DocsViewer() {
  // State for doc list, active doc, content, and sync status
  const [docs, setDocs] = useState<string[]>([])
  const [activeDoc, setActiveDoc] = useState<string | null>(null)
  const [content, setContent] = useState<string>("")
  const [syncing, setSyncing] = useState<boolean>(false)
  const [syncStatus, setSyncStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  /**
   * Load the list of available Markdown files from the backend.
   */
  const loadDocs = async () => {
    if (!apiUrl) {
      setError("API URL not configured")
      return
    }
    try {
      const res = await fetch(`${apiUrl}/docs/list`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setDocs(data.files || [])
    } catch (err) {
      console.error("Failed to load docs list:", err)
      setError("Could not load docs list.")
    }
  }

  /**
   * Fetch content for the selected document.
   */
  const loadContent = async (path: string) => {
    if (!apiUrl) {
      setError("API URL not configured")
      return
    }
    try {
      const res = await fetch(
        `${apiUrl}/docs/view?path=${encodeURIComponent(path)}`
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setContent(data.content || "")
    } catch (err) {
      console.error("Failed to load doc content:", err)
      setError("Could not load document content.")
    }
  }

  /**
   * Trigger Google Docs sync and refresh the list.
   */
  const handleSync = async () => {
    if (!apiUrl) {
      setSyncStatus("API URL not configured")
      return
    }
    setSyncing(true)
    setSyncStatus(null)
    try {
      const res = await fetch(`${apiUrl}/docs/sync`, { method: "POST" })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSyncStatus(`✅ Synced ${data.synced_docs.length} docs.`)
      await loadDocs()
    } catch (err) {
      console.error("Sync error:", err)
      setSyncStatus(`❌ Sync failed: ${err}`)
    } finally {
      setSyncing(false)
    }
  }

  // Initial load of docs list
  useEffect(() => {
    loadDocs()
  }, [])

  // Load content when activeDoc changes
  useEffect(() => {
    if (activeDoc) {
      loadContent(activeDoc)
    } else {
      setContent("")
    }
  }, [activeDoc])

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
      {/* Sidebar: doc list and sync control */}
      <div className="space-y-4 col-span-1">
        <div className="space-y-2">
          <h2 className="font-semibold">Docs</h2>
          <div className="h-[400px] overflow-auto border rounded-md p-2">
            {error && <p className="text-xs text-red-500">{error}</p>}
            {docs.map((doc) => (
              <Button
                key={doc}
                variant={doc === activeDoc ? "default" : "ghost"}
                className="w-full justify-start text-left"
                onClick={() => setActiveDoc(doc)}
              >
                {doc.replace("imported/", "")}
              </Button>
            ))}
          </div>
        </div>

        {/* Sync button */}
        <div>
          <Button
            onClick={handleSync}
            disabled={syncing}
            className="w-full text-sm"
          >
            {syncing ? "🔄 Syncing..." : "🔄 Sync Google Docs"}
          </Button>
          {syncStatus && (
            <p className="text-xs text-muted-foreground mt-2">{syncStatus}</p>
          )}
        </div>
      </div>

      {/* Viewer for document content */}
      <div className="col-span-3">
        <h2 className="font-semibold mb-2">{activeDoc || 'Select a document'}</h2>
        <div className="h-[400px] overflow-auto border rounded-md p-4 whitespace-pre-wrap text-sm">
          {content || "Select a document to view its content."}
        </div>
      </div>
    </div>
  )
}
