import { useState, useRef } from "react"
import { API_ROOT } from "@/lib/api"

export interface Message {
  user: string
  agent: string
  context?: string
  action?: { type: string; payload: unknown }
  id?: string
  status?: "pending" | "approved" | "denied"
}

export function useAskAgent(userId: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)

  const sendQuery = async (
    query: string,
    files: string[],
    topics: string[],
    scrollToBottom: () => void
  ) => {
    if (!query.trim()) return
    setLoading(true)

    try {
      const res = await fetch(`${API_ROOT}/ask?debug=true`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          question: query,
          files,
          topics,
        }),
      })

      const data = await res.json()
      setMessages(prev => [
        ...prev,
        {
          user: query,
          agent: data?.response ?? "[no answer]",
          context: data?.context,
          action: data?.action,
          id: data?.id,
          status: "pending",
        },
      ])
      scrollToBottom()
    } catch {
      setMessages(prev => [
        ...prev,
        {
          user: query,
          agent: "Error contacting Relay.",
        },
      ])
    }

    setLoading(false)
  }

  const updateActionStatus = async (
    id: string,
    action: "approve" | "deny",
    idx: number
  ) => {
    try {
      await fetch(`${API_ROOT}/control/${action}_action`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ id, comment: "inline approval" }),
      })

      setMessages(prev => {
        const updated = [...prev]
        updated[idx] = {
          ...updated[idx],
          status: action === "approve" ? "approved" : "denied",
        }
        return updated
      })
    } catch {
      alert("Error approving/denying action.")
    }
  }

  return {
    messages,
    setMessages,
    sendQuery,
    updateActionStatus,
    loading,
  }
}
