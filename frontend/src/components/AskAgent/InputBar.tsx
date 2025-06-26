// File: components/AskAgent/InputBar.tsx

import React from "react";

type Props = {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  loading: boolean;
};

const InputBar: React.FC<Props> = ({ value, onChange, onSend, loading }) => {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
      className="flex items-center gap-2 mt-4"
      autoComplete="off"
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
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
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
