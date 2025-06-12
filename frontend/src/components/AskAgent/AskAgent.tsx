"use client";

import { useState, useRef } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";

const USER_ID = "bret-demo"; // TODO: Replace with real session/user

type Message = {
  user: string;
  agent: string;
  context?: string;
  // Optionally: action?: { type: string; payload: any };
};

export default function AskAgent() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [showContext, setShowContext] = useState<{ [idx: number]: boolean }>({});

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Send a question to the /ask endpoint and capture response (with context)
  async function sendQuery() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_ROOT}/ask?debug=true`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID,
        },
        body: JSON.stringify({ question: query }),
      });
      const data = await res.json();
      setMessages(prev => [
        ...prev,
        {
          user: query,
          agent: data?.response ?? data?.answer ?? "[no answer]",
          context: data?.context ?? undefined,
          // action: data?.action ?? undefined // Future: agent actions to review
        }
      ]);
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 100);
      setQuery("");
    } catch {
      setMessages(prev => [
        ...prev,
        {
          user: query,
          agent: "Error contacting Relay.",
        }
      ]);
    }
    setLoading(false);
  }

  return (
    <div className="max-w-2xl mx-auto py-8">
      <h2 className="font-bold text-lg mb-4">🤖 Ask the Agent</h2>
      <div className="border rounded-md p-4 mb-4 h-[320px] overflow-auto bg-gray-50">
        {messages.length === 0 && (
          <div className="text-gray-400 italic text-center pt-10">
            Type a question and hit Enter or click &quot;Ask Relay&quot;!
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className="mb-4">
            <div className="font-semibold text-blue-700">You:</div>
            <div className="mb-1 whitespace-pre-wrap">{msg.user}</div>
            <div className="font-semibold text-green-700">Agent:</div>
            <div className="mb-1 whitespace-pre-wrap">{msg.agent}</div>
            {msg.context && (
              <div>
                <Button
                  size="sm"
                  variant="outline"
                  className="my-2"
                  onClick={() =>
                    setShowContext(prev => ({
                      ...prev,
                      [i]: !prev[i]
                    }))
                  }
                >
                  {showContext[i] ? "Hide Context" : "Show Context"}
                </Button>
                {showContext[i] && (
                  <pre className="bg-gray-200 p-2 mt-2 rounded text-xs max-h-32 overflow-auto">
                    {msg.context}
                  </pre>
                )}
              </div>
            )}
            {/* Future: Action review UI, context diff, etc */}
            <hr className="my-2" />
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <form
        className="flex gap-2"
        onSubmit={e => {
          e.preventDefault();
          if (query.trim() && !loading) sendQuery();
        }}
      >
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
      </form>
      <div className="text-xs text-gray-400 mt-2">
        Tip: Click &quot;Show Context&quot; to reveal what code/docs/logs the agent used for each answer.
      </div>
    </div>
  );
}
