// File: components/AskAgent/InputBar.tsx
// Purpose: Text input + send button for AskAgent chat UI
// Updated: 2025-06-30

import React from "react";

type Props = {
  value: string;                 // Input value (controlled)
  onChange: (val: string) => void; // Handle text changes
  onSend: () => void;              // Called to send message
  loading: boolean;                // Loading state (disables input/button)
};

const InputBar: React.FC<Props> = ({ value, onChange, onSend, loading }) => {
  return (
    <form
      className="flex items-center gap-2 mt-4"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        if (!loading && value.trim()) onSend();
      }}
    >
      <input
        type="text"
        className="flex-1 rounded border px-3 py-2"
        placeholder="Type your question…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={loading}
        name="echo-message"
        id="echo-message"
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && value.trim() && !loading) {
            e.preventDefault();
            onSend();
          }
        }}
        autoFocus
      />
      <button
        type="submit"
        className="bg-blue-600 text-white rounded px-4 py-2"
        disabled={loading || !value.trim()}
      >
        {loading ? "Sending…" : "Send"}
      </button>
    </form>
  );
};

export default InputBar;
