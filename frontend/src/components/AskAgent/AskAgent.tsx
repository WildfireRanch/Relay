"use client"

import { useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"

export default function AskAgent() {
  const [query, setQuery] = useState("")
  const [response, setResponse] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // === Send query to Relay backend ===
  async function sendQuery() {
    console.log("🔑 Sending query:", query)
    console.log("🔐 Using key:", process.env.NEXT_PUBLIC_RELAY_KEY)

    if (!query) return
    setLoading(true)
    setResponse(null)

    try {
      // Call Relay backend using correct query param (?question=...)
      const res = await fetch(
        "https://relay.wildfireranch.us/ask?question=" + encodeURIComponent(query),
        {
          headers: {
            "X-API-Key": process.env.NEXT_PUBLIC_RELAY_KEY || ""
          }
        }
      )

      const data = await res.json()
      setResponse(data.response || "No answer.")
    } catch (error) {
      console.error("❌ Failed to get response:", error)
      setResponse("Error contacting Relay.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <Textarea
        placeholder="Ask Echo something..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
      />
      <Button onClick={sendQuery} disabled={loading || !query}>
        {loading ? "Thinking..." : "Ask Echo"}
      </Button>
      {response && (
        <div className="bg-muted p-4 rounded text-sm whitespace-pre-wrap border">
          {response}
        </div>
      )}
    </div>
  )
}
