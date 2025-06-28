// File: src/components/Codex/CodexEditor.tsx
import { Dispatch, SetStateAction } from "react";

export interface Props {
  code: string;
  setCode: Dispatch<SetStateAction<string>>;
}

export default function CodexEditor({ code, setCode }: Props) {
  return (
    <textarea
      value={code}
      onChange={(e) => setCode(e.target.value)}
      className="w-full h-48 p-2 border rounded"
    />
  );
}
