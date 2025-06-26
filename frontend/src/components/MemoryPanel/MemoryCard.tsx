// File: frontend/src/components/MemoryPanel/MemoryCard.tsx

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import Tags from "./Tags"

export type ContextSource = {
  type: string
  title?: string
  path?: string
  tier?: string
  score?: number
  doc_id?: string
}

export type MemoryEntry = {
  timestamp: string
  user: string
  query: string
  topics?: string[]
  files?: string[]
  summary?: string
  context_length?: number
  used_global_context?: boolean
  context_files?: string[]
  files_used?: ContextSource[]
  agent_response?: string
  prompt_length?: number
  response_length?: number
  fallback?: boolean
  tags?: string[]
  saved?: boolean
}

const isNonEmptyArray = <T,>(arr?: T[] | null): arr is T[] =>
  Array.isArray(arr) && arr.length > 0

type Props = {
  m: MemoryEntry
  index: number
  onReplay: (query: string) => void
  onSave: (index: number) => void
  onTagToggle: (index: number, tag: string) => void
  fetchContextFile: (path: string) => void
}

export default function MemoryCard({
  m,
  index,
  onReplay,
  onSave,
  onTagToggle,
  fetchContextFile,
}: Props) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="text-sm font-mono text-muted-foreground">
          {new Date(m.timestamp).toLocaleString()} • {m.user}
        </div>
        <div className="text-sm font-semibold">Query:</div>
        <div className="text-sm">{m.query}</div>

        {isNonEmptyArray(m.topics) && <div className="text-xs">Topics: {m.topics.join(", ")}</div>}
        {isNonEmptyArray(m.files) && <div className="text-xs">Files: {m.files.join(", ")}</div>}

        {isNonEmptyArray(m.context_files) && (
          <div className="text-xs text-blue-800">
            <strong>Context Files:</strong>{" "}
            {m.context_files.map((cf, idx) => (
              <span key={cf}>
                <a className="underline cursor-pointer" onClick={() => fetchContextFile(cf)}>
                  {cf}
                </a>
                {idx < m.context_files!.length - 1 ? ", " : ""}
              </span>
            ))}
          </div>
        )}

        {isNonEmptyArray(m.files_used) && (
          <div className="text-xs text-purple-700">
            <strong>Injected:</strong>{" "}
            {m.files_used.map((f, idx) => (
              <span key={idx}>
                <span
                  className="underline cursor-pointer"
                  onClick={() => f.path && fetchContextFile(f.path)}
                >
                  {f.path || f.title || f.doc_id || f.type}
                </span>
                {f.tier && <span className="ml-1 text-gray-500">[{f.tier}]</span>}
                {idx < m.files_used!.length - 1 ? ", " : ""}
              </span>
            ))}
          </div>
        )}

        <div className="text-xs text-gray-600">
          {typeof m.context_length === "number" && <>Context Length: {m.context_length} chars<br /></>}
          {typeof m.prompt_length === "number" && <>Prompt: {m.prompt_length}, Response: {m.response_length}</>}
        </div>

        {m.used_global_context && (
          <span className="inline-block px-2 py-1 text-xs bg-green-100 text-green-700 rounded">Global context</span>
        )}
        {m.fallback && (
          <span className="inline-block px-2 py-1 text-xs bg-orange-100 text-orange-700 rounded">Fallback</span>
        )}

       {Array.isArray(m.tags) && m.tags.length > 0 && (
       <div className="text-xs text-blue-600">
       <strong>Tags:</strong> {m.tags.join(", ")}
       </div>

        )}

        {m.summary && (
          <pre className="bg-muted p-2 rounded text-xs whitespace-pre-wrap">{m.summary}</pre>
        )}

        <div className="flex gap-2 flex-wrap text-xs mt-2">
          {["important", "bug", "training", "review"].map(tag => (
            <Button
              key={tag}
              variant={m.tags?.includes(tag) ? "default" : "outline"}
              size="sm"
              onClick={() => onTagToggle(index, tag)}
            >
              {tag}
            </Button>
          ))}
          <Button
            variant={m.saved ? "default" : "outline"}
            size="sm"
            onClick={() => onSave(index)}
          >
            {m.saved ? "💾 Saved" : "Save"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onReplay(m.query)}>
            🔁 Replay
          </Button>
        </div>

        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-blue-700">Debug: Raw Entry</summary>
          <pre className="bg-gray-100 p-2 rounded text-xs overflow-auto">{JSON.stringify(m, null, 2)}</pre>
        </details>
      </CardContent>
    </Card>
  )
}
