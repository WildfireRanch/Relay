"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

// === TypeScript types for queued actions ===
type Action = {
  id: string
  timestamp: string
  status: string
  action: {
    type: string
    path?: string
    content?: string
  }
}

// === ActionQueue Component ===
export default function ActionQueuePanel() {
  const [actions, setActions] = useState<Action[]>([])            // Holds queued actions
  const [approving, setApproving] = useState<string | null>(null) // Tracks which item is being approved

  // === Fetch all queued actions from the backend ===
  async function fetchQueue() {
    const res = await fetch("https://relay.wildfireranch.us/control/list_queue", {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      }
    })
    const data = await res.json()
    setActions(data.actions || [])
  }

  // === Approve a single action by ID ===
  async function approve(id: string) {
    setApproving(id)
    await fetch("https://relay.wildfireranch.us/control/approve_action", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      },
      body: JSON.stringify({ id })
    })
    await fetchQueue() // Refresh queue after approval
    setApproving(null)
  }

  // === Load queue on first render ===
  useEffect(() => {
    fetchQueue()
  }, [])

  // === Empty state ===
  if (!actions.length) {
    return <p className="text-muted-foreground">No actions in queue.</p>
  }

  // === Render each queued action as a card ===
  return (
    <div className="space-y-4">
      {actions.map((a) => (
        <Card key={a.id}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">
              #{a.id.slice(0, 8)} • {a.timestamp}
            </div>
            <div className="text-sm">
              <strong>Type:</strong> {a.action.type}
              {a.action.path && (
                <span className="ml-2"><strong>Path:</strong> {a.action.path}</span>
              )}
            </div>
            <pre className="bg-muted p-2 rounded text-sm overflow-auto whitespace-pre-wrap">
              {a.action.content?.slice(0, 500) || "No content"}
            </pre>
            <Button
              variant="default"
              onClick={() => approve(a.id)}
              disabled={approving === a.id}
            >
              {approving === a.id ? "Approving..." : "Approve"}
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
