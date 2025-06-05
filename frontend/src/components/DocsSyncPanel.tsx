// File: components/DocsSyncPanel.tsx
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"

export default function DocsSyncPanel() {
  const [status, setStatus] = useState<string>("")

  const triggerSync = async (endpoint: string) => {
    setStatus("⏳ Running...")
    try {
      const res = await fetch(`https://relay.wildfireranch.us/docs/${endpoint}`, { method: "POST" })
      const data = await res.json()
      setStatus(`✅ ${data.message || "Done"}`)
    } catch (err) {
      console.error(err)
      setStatus("❌ Failed to sync")
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">🧠 Sync & Refresh Docs</h2>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => triggerSync("sync")}>🔄 Sync Google Docs</Button>
        <Button onClick={() => triggerSync("refresh_kb")}>🧠 Refresh KB</Button>
        <Button onClick={() => triggerSync("full_sync")}>🚀 Full Sync</Button>
      </div>
      {status && <div className="mt-2 text-sm text-muted-foreground">{status}</div>}
    </div>
  )
}
