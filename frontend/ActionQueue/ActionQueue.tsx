"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

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

export default function ActionQueue() {
  const [actions, setActions] = useState<Action[]>([])
  const [approving, setApproving] = useState<string | null>(null)

  async function fetchQueue() {
    const res = await fetch("https://relay.wildfireranch.us/control/list_queue", {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      }
    })
    const data = await res.json()
    setActions(data.actions || [])
  }

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
    await fetchQueue()
    setApproving(null)
  }

  useEffect(() => {
    fetchQueue()
  }, [])

  if (!actions.length) return <p className="text-muted-foreground">No actions in queue.</p>

  return (
    <div className="space-y-4">
      {actions.map((a) => (
        <Card key={a.id}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">#{a.id.slice(0, 8)}</div>
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
