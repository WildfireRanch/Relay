// File: frontend/src/app/control/page.tsx
// Purpose: Admin control dashboard with patch queue, logs, and memory panels

import ActionQueuePanel from "@/components/ActionQueue/ActionQueuePanel";
import LogsPanel from "@/components/LogsPanel/LogsPanel";
import MemoryPanel from "@/components/MemoryPanel";
import GmailOpsPanel from "@/components/GmailOps/GmailOpsPanel";

export default function ControlPage() {
  return (
    <main className="p-6 space-y-6">
      <h1 className="text-2xl font-bold mb-4">🧠 Relay Control Center</h1>

      <section>
        <h2 className="text-xl font-semibold mb-2">📝 Pending Actions</h2>
        <ActionQueuePanel />
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-2">📄 Execution Logs</h2>
        <LogsPanel />
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-2">🧬 Memory Log</h2>
        <MemoryPanel />
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-2">✉️ Email Operations</h2>
        <GmailOpsPanel />
      </section>
    </main>
  );
}
