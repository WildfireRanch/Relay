// File: components/DocsViewer/DocsViewer.tsx
"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"

export default function DocsViewer() {
  const [docs, setDocs] = useState<string[]>([])
  const [activeDoc, setActiveDoc] = useState<string | null>(null)
  const [content, setContent] = useState<string>("")

  // Fetch available document filenames on mount
  useEffect(() => {
    fetch("https://relay.wildfireranch.us/docs/list")
      .then(res => res.json())
      .then(data => setDocs(data.files || []))
  }, [])

  // Fetch selected document content
  useEffect(() => {
    if (activeDoc) {
      fetch(`https://relay.wildfireranch.us/docs/view?path=${encodeURIComponent(activeDoc)}`)
        .then(res => res.json())
        .then(data => setContent(data.content || ""))
    }
  }, [activeDoc])

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
      {/* Sidebar: Document list */}
      <div className="space-y-2 col-span-1">
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
