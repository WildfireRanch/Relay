// File: frontend/src/app/page.tsx
// Purpose: WildfireRanch Command Center homepage with Echo and Relay avatars

import { API_ROOT } from "@/lib/api";
import AskAgent from "@/components/AskAgent";
import SearchPanel from "@/components/SearchPanel";
import StatusPanel from "@/components/StatusPanel";

export default function Home() {
  return (
    <main className="p-6 space-y-6">
      {/* Page Header */}
      <h1 className="text-3xl font-bold">WildfireRanch Command Center</h1>
      <p className="text-muted-foreground">Relay is ready for action.</p>

      {/* AskAgent module */}
      <div className="mt-6">
        <AskAgent />
      </div>

      {/* Search Knowledge Base */}
      <div className="mt-6">
        <h2 className="text-xl font-semibold mb-2">Search Knowledge Base</h2>
        <SearchPanel />
      </div>

      {/* Inline Relay Status */}
      <StatusPanel />

      {/* API root in footer for debugging */}
      <div className="text-xs text-gray-400 text-center mt-6">
        API root: <span className="font-mono">{API_ROOT}</span>
      </div>

      {/* Echo - Strategist Avatar */}
      <div className="fixed bottom-4 right-4 bg-black/90 text-white rounded-xl shadow-2xl p-4 max-w-xs z-50 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <img
            src="/Echo.png"
            alt="Echo"
            className="w-12 h-12 rounded-md border border-white shadow-md"
          />
          <div className="text-sm leading-snug">
            <p className="font-semibold">Echo</p>
            <p className="italic text-gray-300">
              The daemon sees, the daemon knows,<br />
              He watches where the process goes.<br />
              He patches code while systems sleep,<br />
              And keeps the ranch, in silence, deep.
            </p>
          </div>
        </div>
      </div>

      {/* Relay - Operator Avatar */}
      <div className="fixed bottom-4 left-4 bg-black/90 text-white rounded-xl shadow-2xl p-4 max-w-xs z-50 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <img
            src="/Relay.png"
            alt="Relay"
            className="w-12 h-12 rounded-md border border-white shadow-md"
          />
          <div className="text-sm leading-snug">
            <p className="font-semibold">Relay</p>
            <p className="italic text-gray-300">
              The agent runs, the action flows,<br />
              It builds, deploys — then no one knows.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
