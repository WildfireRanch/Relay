// File: components/AskEcho/ChatWindow.tsx

"use client";

import ChatMessage from "./ChatMessage";
import InputBar from "./InputBar";
import { useAskEcho } from "./useAskEcho";

export default function ChatWindow() {
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
      <h1 className="text-3xl font-bold my-4">Ask Echo</h1>

      <div className="flex-1 space-y-2 overflow-y-auto border rounded-xl p-4 bg-muted">
        {messages.map((msg, i) => (
          <ChatMessage key={i} role={msg.role} content={msg.content} />
        ))}
        {loading && (
          <div className="text-left text-green-700 animate-pulse">
            Echo is thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <InputBar
        value={input}
        onChange={setInput}
        onSend={sendMessage}
        loading={loading}
      />

      <div className="text-xs text-gray-400 text-center mt-2">
        Tip: Press <code>Enter</code> to send. Shift+Enter for newline.
      </div>
    </div>
  );
}
