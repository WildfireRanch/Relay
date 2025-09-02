// File: components/AskAgent/InputBar.tsx
// Purpose: Text input + send button for AskAgent chat UI (normalized /ask flow)
// Updated: 2025-09-02
//
// Notes:
// - Drop-in compatible: same Props (value, onChange, onSend, loading)
// - Enter sends; Shift+Enter inserts newline (safer for longer prompts)
// - Prevents double-send, disables while loading
// - Accessible labels + keyboard-friendly

"use client";

import React, { useCallback, useRef } from "react";

type Props = {
  value: string;                      // controlled input value
  onChange: (val: string) => void;    // update text
  onSend: () => void;                 // trigger send
  loading: boolean;                   // disable while pending
};

const InputBar: React.FC<Props> = ({ value, onChange, onSend, loading }) => {
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Send guard (no-ops if empty/whitespace or loading)
  const trySend = useCallback(() => {
    const v = value.trim();
    if (!v || loading) return;
    onSend();
  }, [value, loading, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // IME safety: only act if not composing
            if (e.nativeEvent?.isComposing) return;

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        trySend();
      }
    },
    [trySend]
  );

  return (
    <form
      className="flex items-end gap-2 mt-3"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        trySend();
      }}
      aria-label="Ask Echo input"
    >
      <label htmlFor="echo-message" className="sr-only">
        Ask Echo
      </label>

      <textarea
        id="echo-message"
        name="echo-message"
        ref={taRef}
        className="flex-1 min-h-[44px] max-h-48 rounded border bg-background px-3 py-2 text-sm leading-5"
        placeholder="Type your question… (Shift+Enter for newline)"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading}
        rows={2}
      />

      <button
        type="submit"
        className="rounded px-4 py-2 text-sm border shadow-sm disabled:opacity-50"
        disabled={loading || !value.trim()}
        aria-busy={loading}
        aria-label="Send message"
      >
        {loading ? "Sending…" : "Send"}
      </button>
    </form>
  );
};

export default InputBar;
