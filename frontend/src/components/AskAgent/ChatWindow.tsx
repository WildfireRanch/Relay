// File: components/AskEcho/ChatWindow.tsx
// Purpose: Chat window for Ask Echo UI using /mcp/run pipeline
// Updated: 2025-07-01

"use client";

import ChatMessage from "./ChatMessage";
import InputBar from "./InputBar";
import { useAskEcho } from "./useAskEcho";
import { toMDString } from "@/lib/toMDString";

export default function ChatWindow() {
  // Unified chat state and actions from the custom hook
  const {
    input,
    setInput,
    messages,
    sendMessage,
    loading,
    bottomRef,
  } = useAskEcho();

  return (
    <div className="w-full max-w-2xl mx-auto min-h-screen flex flex-col">
      {/* Header */}
      <h1 className="text-3xl font-bold my-4">Ask Echo</h1>

      {/* Message List */}
      <div className="flex-1 space-y-2 overflow-y-auto border rounded-xl p-4 bg-muted">
        {messages.map((msg, i) => (
          <>
            {typeof msg.content !== "string" &&
              console.log("DEBUG 418:", typeof msg.content, msg.content)}
            <ChatMessage key={i} role={msg.role} content={toMDString(msg.content)} />
          </>
        ))}
        {loading && (
          <div className="text-left text-green-700 animate-pulse">
            Echo is thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Bar */}
      <InputBar
        value={input}
        onChange={setInput}
        onSend={sendMessage}
        loading={loading}
      />

      {/* Keyboard shortcut hint */}
      <div className="text-xs text-gray-400 text-center mt-2">
        Tip: Press <code>Enter</code> to send. Shift+Enter for newline.
      </div>
    </div>
  );
}
