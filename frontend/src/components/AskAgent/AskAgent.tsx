// File: components/AskAgent/AskAgent.tsx
// Directory: frontend/src/components/AskAgent
// Purpose: Main Relay AI chat input and display component

"use client";

import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api"; // Centralized API root

const USER_ID = "bret-demo"; // TODO: Replace with real user/session logic in production

export default function AskAgent() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Send a question to the Relay backend's /ask endpoint
  async function sendQuery() {
    if (!query.trim()) return;
    setLoading(true);
    setResponse(null);
    try {
      const res = await fetch(`${API_ROOT}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({ question: query }),
      });

      const data = await res.json();
      setResponse(data?.response ?? data?.answer ?? "[no answer]");
    } catch (error) {
      console.error("❌ Failed to get response:", error);
      setResponse("Error contacting Relay.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <Textarea
        placeholder="Ask Relay something..."
        value={query}
        onChange={e => setQuery(e.target.value)}
        disabled={loading}
        name="relay-query"
        id="relay-query"
        onKeyDown={e => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendQuery();
          }
        }}
      />
      <Button onClick={sendQuery} disabled={loading || !query.trim()}>
        {loading ? "Thinking..." : "Ask Relay"}
      </Button>
      {response && (
        <div className="bg-muted p-4 rounded text-sm whitespace-pre-wrap border mt-2">
          {response}
        </div>
      )}
    </div>
  );
}
