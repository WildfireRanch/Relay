// File: components/AskEcho/ChatWindow.tsx
// Purpose: Chat window for Ask Echo UI using normalized /ask pipeline
// Updated: 2025-09-02
//
// Changes:
// - Uses the production useAskEcho() (POST /ask) from components/AskAgent/useAskEcho
// - Renders normalized messages with ChatMessage (content/error/context/meta/status)
// - Adds a compact controls bar for role/files/topics/debug
// - Uses per-message context toggles via showContext/toggleContext from the hook
// - Removes legacy toMDString() at render time (hook already coerces)

"use client";

import ChatMessage from "@/components/AskAgent/ChatMessage"; // updated message bubble
import InputBar from "./InputBar";                            // keep your existing input UI
import { useAskEcho } from "@/components/AskAgent/useAskEcho";
import React from "react";

export default function ChatWindow() {
  // Unified chat state and actions from the custom hook
  const {
    input,
    setInput,
    messages,
    sendMessage,
    loading,
    bottomRef,

    // Controls surfaced by the new hook
    files,
    setFiles,
    topics,
    setTopics,
    role,
    setRole,
    debug,
    setDebug,

    // Context toggles
    showContext,
    toggleContext,
  } = useAskEcho();

  return (
    <div className="w-full max-w-3xl mx-auto min-h-screen flex flex-col gap-3">
      {/* Header */}
      <header className="flex items-center justify-between mt-4">
        <h1 className="text-3xl font-bold">Ask Echo</h1>
        <div className="text-xs text-muted-foreground">
          Normalized pipeline · <code>/ask</code>
        </div>
      </header>

      {/* Controls bar */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <label className="flex flex-col text-sm">
          <span className="mb-1 font-medium">Role</span>
          <select
            className="rounded border bg-background px-2 py-1"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="planner">planner</option>
            <option value="codex">codex</option>
            <option value="docs">docs</option>
            <option value="control">control</option>
          </select>
        </label>

        <label className="flex flex-col text-sm md:col-span-2">
          <span className="mb-1 font-medium">Files (CSV)</span>
          <input
            className="rounded border bg-background px-2 py-1"
            placeholder="e.g. docs/plan.md, agents/planner_agent.py"
            value={files}
            onChange={(e) => setFiles(e.target.value)}
          />
        </label>

        <label className="flex items-center gap-2 justify-between text-sm">
          <span className="font-medium">Debug</span>
          <input
            type="checkbox"
            className="size-4"
            checked={debug}
            onChange={(e) => setDebug(e.target.checked)}
          />
        </label>

        <label className="flex flex-col text-sm md:col-span-3">
          <span className="mb-1 font-medium">Topics (CSV)</span>
          <input
            className="rounded border bg-background px-2 py-1"
            placeholder="e.g. solar, miner, kb:sol-ark"
            value={topics}
            onChange={(e) => setTopics(e.target.value)}
          />
        </label>
      </section>

      {/* Message List */}
      <div className="flex-1 space-y-3 overflow-y-auto border rounded-xl p-4 bg-muted">
        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            role={msg.role}
            content={msg.content}              // already markdown-coerced by hook
            error={msg.error ?? null}          // show request/network errors inline
            context={msg.context}              // optional (shown behind a toggle)
            meta={msg.meta ?? null}            // origin, timings, request_id, etc.
            status={msg.status}                // pending/approved/denied (actions)
            isContextOpen={!!showContext[i]}   // controlled expand/collapse
            onToggleContext={() => toggleContext(i)}
            showExtras={true}                  // show context/meta sections when present
            className={msg.role === "user" ? "" : ""}
          />
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
      <div className="text-xs text-muted-foreground text-center mb-4">
        Tip: Press <code>Enter</code> to send. Shift+Enter for newline.
      </div>
    </div>
  );
}
