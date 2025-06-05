// File: frontend/src/app/page.tsx

import AskAgent from "@/components/AskAgent/AskAgent"
import Link from "next/link"
import SearchPanel from "@/components/SearchPanel"
import StatusPanel from "@/components/StatusPanel"

export default function Home() {
  return (
    <main className="p-6 space-y-6">
      <h1 className="text-3xl font-bold">CommandCenter</h1>
      <p className="text-muted-foreground">Your Relay agent is ready for action.</p>

      {/* === Quick Navigation === */}
      <div className="mt-4 space-x-4 text-sm text-muted-foreground">
        <Link href="/docs" className="underline hover:text-foreground">📚 Docs</Link>
        <Link href="/control" className="underline hover:text-foreground">🛠️ Control</Link>
        <Link href="/status" className="underline hover:text-foreground">📊 Status</Link>
      </div>

      {/* === AskAgent module === */}
      <div className="mt-6">
        <AskAgent />
      </div>

      {/* === Search Knowledge Base === */}
      <div className="mt-6">
        <h2 className="text-xl font-semibold mb-2">Search Knowledge Base</h2>
        <SearchPanel />
      </div>

      {/* === Inline Relay Status === */}
      <StatusPanel />
    </main>
  )
}
