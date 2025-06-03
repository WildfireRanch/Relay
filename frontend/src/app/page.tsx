// app/page.tsx
import AskAgent from "@/components/AskAgent/AskAgent"
import Link from "next/link"
import SearchPanel from "@/components/SearchPanel"

export default function Home() {
  return (
    <main className="p-6 space-y-6">
      <h1 className="text-3xl font-bold">CommandCenter</h1>
      <p className="text-muted-foreground">Your Relay agent is ready for action.</p>

      {/* === AskAgent module === */}
      <div className="mt-6">
        <AskAgent />
      </div>

      {/* === Search Knowledge Base === */}
      <div className="mt-6">
        <h2 className="text-xl font-semibold mb-2">Search Knowledge Base</h2>
        <SearchPanel />
      </div>

      {/* === Link to Docs Viewer === */}
      <div className="mt-6">
        <Link href="/docs" className="text-blue-600 hover:underline">
          View All Synced Docs →
        </Link>
      </div>
    </main>
  )
}