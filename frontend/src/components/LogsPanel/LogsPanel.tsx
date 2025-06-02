"use client"

import { useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"

type LogEntry = {
  id: string
  timestamp: string
  type: string
  path?: string
  status: string
  result?: any
}

export default function LogsPanel() {
  const [log, setLog] = useState<LogEntry[]>([])

  async function fetchLog() {
    const res = await fetch("https://relay.wildfireranch.us/control/list_log", {
      headers: {
        "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
      }
    })
    const data = await res.json()
    setLog(data.log || [])
  }

  useEffect(() => {
    fetchLog()
  }, [])

  if (!log.length) return <p className="text-muted-foreground">No log entries yet.</p>

  return (
    <div className="space-y-4">
      {log.map((entry) => (
        <Card key={entry.id}>
          <CardContent className="p-4 space-y-2">
            <div className="text-sm font-mono text-muted-foreground">
              #{entry.id.slice(0, 8)} • {entry.timestamp}
            </div>
            <div className="text-sm">
              <strong>Type:</strong> {entry.type}{" "}
              {entry.path && (
                <span className="ml-2"><strong>Path:</strong> {entry.path}</span>
              )}
            </div>
            <pre className="bg-muted p-2 rounded text-sm overflow-auto whitespace-pre-wrap">
              {JSON.stringify(entry.result, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
