// File: components/AskAgent/InputBar.tsx
// Purpose: Text input + send button for AskAgent chat UI (normalized /ask flow)
// Updated: 2025-09-02
//
// Notes:
// - Enter sends; Shift+Enter adds newline (IME-safe)
// - Single disabled flag; prevents double-send
// - A11y labels; TS-safe composition guard

"use client";

import React, { useCallback, useRef } from "react";

type Props = {
  value: string;                   // controlled input value
  onChange: (val: string) => void; // update text
  onSend: () => void;              // trigger send
  loading: boolean;                // disable while pending
};

const InputBar: React.FC<Props> = ({ value, onChange, onSend, loading }) => {
  const taRef = useRef<HTMLTextAreaElement>(null);

  const trySend = useCallback(() => {
    const v = value.trim();
    if (!v || loading) return;
    onSend();
  }, [value, loading, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Some TS dom typings don’t include isComposing on KeyboardEvent.
      const isComposing =
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (e.nativeEvent as any)?.isComposing === true;

      if (isComposing) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        trySend();
      }
    },
    [trySend]
  );

  const disabled = loading || value.trim().length === 0;

  return (
    <form
      className="mt-3 flex items-end gap-2"
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
        aria-disabled={loading}
      />

      <button
        type="submit"
        className="rounded border px-4 py-2 text-sm shadow-sm disabled:opacity-50"
        disabled={disabled}
        aria-busy={loading}
        aria-label="Send message"
      >
        {loading ? "Sending…" : "Send"}
      </button>
    </form>
  );
};

export default InputBar;
