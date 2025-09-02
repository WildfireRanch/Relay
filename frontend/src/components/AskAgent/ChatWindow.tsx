// File: components/AskEcho/ChatWindow.tsx
// Purpose: Chat window for Ask Echo UI using normalized /ask pipeline
// Updated: 2025-09-02
//
// Changes:
// - Uses the production useAskEcho() (POST /ask) from components/AskAgent/useAskEcho
// - Renders normalized messages with ChatMessage (content/error/context/meta/status)
// - Adds a compact controls bar for role/files/topics/debug
// - Uses per-message context toggles via showContext/toggleContext from the hook
// - Marks the feed as aria-live and uses stable-ish keys per message

"use client";

import React from "react";
import ChatMessage from "@/components/AskAgent/ChatMessage"; // updated message bubble
import InputBar from "./InputBar";                            // keep your existing input UI
import { useAskEcho } from "@/components/AskAgent/useAskEcho";

type Role = "planner" | "codex" | "docs" | "control";

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
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-3">
      {/* Header */}
      <header className="mt-4 flex items-center justify-between">
        <h1 className="text-3xl font-bold">Ask Echo</h1>
        <div className="text-xs text-muted-foreground">
          Normalized pipeline · <code>/ask</code>
        </div>
      </header>

      {/* Controls bar */}
      <section className="grid grid-cols-1 gap-2 md:grid-cols-4">
        <label className="flex flex-col text-sm">
          <span className="mb-1 font-medium">Role</span>
          <select
            className="rounded border bg-background px-2 py-1"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            aria-label="Agent role"
          >
            <option value="planner">planner</option>
            <option value="codex">codex</option>
            <option value="docs">docs</option>
            <option value="control">control</option>
          </select>
        </label>

        <label className="md:col-span-2 flex flex-col text-sm">
          <span className="mb-1 font-medium">Files (CSV)</span>
          <input
            className="rounded border bg-background px-2 py-1"
            placeholder="e.g. docs/plan.md, agents/planner_agent.py"
            value={files}
            onChange={(e) => setFiles(e.target.value)}
            aria-label="Files to include (comma separated)"
          />
        </label>

        <label className="flex items-center justify-between gap-2 text-sm">
          <span className="font-medium">Debug</span>
          <input
            type="checkbox"
            className="size-4"
            checked={debug}
            onChange={(e) => setDebug(e.target.checked)}
            aria-label="Toggle debug context"
          />
        </label>

        <label className="md:col-span-3 flex flex-col text-sm">
          <span className="mb-1 font-medium">Topics (CSV)</span>
          <input
            className="rounded border bg-background px-2 py-1"
            placeholder="e.g. solar, miner, kb:sol-ark"
            value={topics}
            onChange={(e) => setTopics(e.target.value)}
            aria-label="Topics to include (comma separated)"
          />
        </label>
      </section>

      {/* Message List */}
      <div
        className="flex-1 space-y-3 overflow-y-auto rounded-xl border bg-muted p-4"
        // Announce updates politely; avoids double speech from nested content
        role="log"
        aria-live="polite"
        aria-relevant="additions"
      >
        {messages.length === 0 && !loading && (
          <div className="text-center text-sm text-muted-foreground">
            Start the conversation — ask Echo anything.
          </div>
        )}

        {messages.map((msg, i) => {
          // Prefer a server-provided id; otherwise derive a stable-ish key
          const key = `msg-${msg.id ?? ""}-${i}`;
          return (
            <ChatMessage
              key={key}
              role={msg.role}
              content={msg.content}              // already markdown-coerced by hook
              error={msg.error ?? null}          // show request/network errors inline
              context={msg.context}              // optional (shown behind a toggle)
              meta={msg.meta ?? null}            // origin, timings, request_id, etc.
              status={msg.status}                // pending/approved/denied (actions)
              isContextOpen={!!showContext[i]}   // controlled expand/collapse
              onToggleContext={() => toggleContext(i)}
              showExtras={true}                  // show context/meta sections when present
            />
          );
        })}

        {loading && (
          <div className="animate-pulse text-left text-green-700">
            Echo is thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Bar */}
      <InputBar value={input} onChange={setInput} onSend={sendMessage} loading={loading} />

      {/* Keyboard shortcut hint */}
      <div className="mb-4 text-center text-xs text-muted-foreground">
        Tip: Press <code>Enter</code> to send. Shift+Enter for newline.
      </div>
    </div>
  );
}
