// File: components/AskAgent.tsx
"use client"

import { useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"

export default function AskAgent() {
  const [query, setQuery] = useState("")
  const [response, setResponse] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // === Sends a question to the Relay backend's /ask endpoint ===
  async function sendQuery() {
    console.log("🔑 Sending query:", query)
    console.log("🔐 Using key:", process.env.NEXT_PUBLIC_RELAY_KEY)

    if (!query) return
    setLoading(true)
    setResponse(null)

    try {
      // Make a GET request without triggering CORS preflight
      const res = await fetch(
        "https://relay.wildfireranch.us/ask?question=" + encodeURIComponent(query),
        {
          method: "GET"
        }
      )

      // Log raw response
      console.log("📦 Raw response:", res)

      // Try to parse JSON and log it
      const data = await res.json().catch(err => {
        console.error("❌ Failed to parse JSON:", err)
        return { error: "Invalid JSON response" }
      })

      console.log("📨 Parsed response:", data)

      // Display response from backend
      setResponse(data?.response ?? data?.answer ?? "No answer.")
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
        placeholder="Ask Relay something..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
      />
      <Button onClick={sendQuery} disabled={loading || !query}>
        {loading ? "Thinking..." : "Ask Relay"}
      </Button>
      {response && (
        <div className="bg-muted p-4 rounded text-sm whitespace-pre-wrap border">
          {response}
        </div>
      )}
    </div>
  )
}
