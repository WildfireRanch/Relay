// File: components/DocsViewer/DocsViewer.tsx
"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"

export default function DocsViewer() {
  const [docs, setDocs] = useState<string[]>([])
  const [activeDoc, setActiveDoc] = useState<string | null>(null)
  const [content, setContent] = useState<string>("")
  const [syncing, setSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState<string | null>(null)

  // Fetch available document filenames on mount or after sync
  const loadDocs = () => {
    fetch("https://relay.wildfireranch.us/docs/list")
      .then(res => res.json())
      .then(data => setDocs(data.files || []))
  }

  useEffect(() => {
    loadDocs()
  }, [])

  // Fetch selected document content
  useEffect(() => {
    if (activeDoc) {
      fetch(`https://relay.wildfireranch.us/docs/view?path=${encodeURIComponent(activeDoc)}`)
        .then(res => res.json())
        .then(data => setContent(data.content || ""))
    }
  }, [activeDoc])

  // Trigger backend sync of Google Docs
  const handleSync = async () => {
    setSyncing(true)
    setSyncStatus(null)
    try {
      const res = await fetch("https://relay.wildfireranch.us/docs/sync_google", {
        method: "POST",
      })
      const data = await res.json()
      setSyncStatus(data.status || "✅ Sync complete")
      loadDocs() // Refresh doc list after sync
    } catch (err) {
      setSyncStatus("❌ Sync failed")
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
      {/* Sidebar: Document list and sync control */}
      <div className="space-y-4 col-span-1">
        <div className="space-y-2">
          <h2 className="font-semibold">Docs</h2>
          <div className="h-[400px] overflow-auto border rounded-md p-2">
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

        {/* Sync Button */}
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

      {/* Content viewer */}
      <div className="col-span-3">
        <h2 className="font-semibold mb-2">{activeDoc}</h2>
        <div className="h-[400px] overflow-auto border rounded-md p-4 whitespace-pre-wrap text-sm">
          {content || "Select a document to view its content."}
        </div>
      </div>
    </div>
  )
}
