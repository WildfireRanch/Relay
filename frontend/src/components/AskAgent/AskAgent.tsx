// File: AskAgent.tsx
// Directory: frontend/src/components
// Purpose: Agent query panel with inline patch review, context toggles, and live control queue integration

"use client";

import { useState, useRef } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";

const USER_ID = "bret-demo"; // TODO: Replace with real session/user

interface Message {
  user: string;
  agent: string;
  context?: string;
  action?: { type: string; payload: any };
  id?: string;
  status?: "pending" | "approved" | "denied";
}

export default function AskAgent() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [showContext, setShowContext] = useState<{ [idx: number]: boolean }>({});
  const [files, setFiles] = useState("");
  const [topics, setTopics] = useState("");

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

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
        body: JSON.stringify({
          question: query,
          files: files ? files.split(",").map(f => f.trim()) : undefined,
          topics: topics ? topics.split(",").map(t => t.trim()) : undefined
        })
      });
      const data = await res.json();
      setMessages((prev: Message[]) => [
        ...prev,
        {
          user: query,
          agent: data?.response ?? "[no answer]",
          context: data?.context,
          action: data?.action,
          id: data?.id,
          status: "pending"
        }
      ]);
      setQuery("");
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch {
      setMessages((prev: Message[]) => [
        ...prev,
        {
          user: query,
          agent: "Error contacting Relay."
        }
      ]);
    }
    setLoading(false);
  }

  async function updateActionStatus(id: string, action: "approve" | "deny", idx: number) {
    try {
      await fetch(`${API_ROOT}/control/${action}_action`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": USER_ID
        },
        body: JSON.stringify({ id, comment: "inline approval" })
      });
      setMessages(prev => {
        const updated = [...prev];
        updated[idx] = { ...updated[idx], status: action === "approve" ? "approved" : "denied" };
        return updated;
      });
    } catch (err) {
      alert("Error approving/denying action.");
    }
  }

  return (
    <div className="max-w-2xl mx-auto py-8">
      <h2 className="font-bold text-lg mb-4">🤖 Ask the Agent</h2>

      <div className="mb-4 grid grid-cols-1 gap-2">
        <input
          type="text"
          className="border rounded px-2 py-1 text-sm"
          placeholder="Optional: file paths (comma-separated)"
          value={files}
          onChange={e => setFiles(e.target.value)}
        />
        <input
          type="text"
          className="border rounded px-2 py-1 text-sm"
          placeholder="Optional: topics (e.g. mining, solarshack)"
          value={topics}
          onChange={e => setTopics(e.target.value)}
        />
      </div>

      <div className="border rounded-md p-4 mb-4 h-[320px] overflow-auto bg-gray-50">
        {messages.length === 0 && (
          <div className="text-gray-400 italic text-center pt-10">
            Type a question and hit Enter or click "Ask Relay"!
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className="mb-4">
            <div className="font-semibold text-blue-700">You:</div>
            <div className="mb-1 whitespace-pre-wrap">{msg.user}</div>
            <div className="font-semibold text-green-700">Agent:</div>
            <div className="mb-1 whitespace-pre-wrap">{msg.agent}</div>

            {msg.action && (
              <div className="mt-2 p-2 bg-yellow-100 border rounded text-sm">
                <strong>Agent Suggestion:</strong>
                <pre className="mt-1 whitespace-pre-wrap text-xs">
                  {JSON.stringify(msg.action, null, 2)}
                </pre>
                {msg.id && msg.status === "pending" && (
                  <div className="flex gap-2 mt-2">
                    <Button size="sm" onClick={() => updateActionStatus(msg.id!, "approve", i)}>
                      ✅ Approve
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => updateActionStatus(msg.id!, "deny", i)}>
                      ❌ Deny
                    </Button>
                  </div>
                )}
                {msg.status === "approved" && (
                  <div className="text-green-700 text-xs mt-1">✅ Action approved</div>
                )}
                {msg.status === "denied" && (
                  <div className="text-red-700 text-xs mt-1">❌ Action denied</div>
                )}
              </div>
            )}

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
        Tip: Use optional file/topic fields for scoped context. Click "Show Context" to reveal what code/docs the agent used.
      </div>
    </div>
  );
}
