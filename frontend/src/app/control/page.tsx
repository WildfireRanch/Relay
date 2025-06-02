import ActionQueuePanel from "@/components/ActionQueue/ActionQueuePanel"
import LogsPanel from "@/components/LogsPanel/LogsPanel"

export default function ControlPage() {
  return (
    <main className="p-6 space-y-10">
      <div>
        <h2 className="text-2xl font-bold mb-4">Queued Actions</h2>
        <ActionQueuePanel />
      </div>
      <div>
        <h2 className="text-2xl font-bold mb-4">Executed Log</h2>
        <LogsPanel />
      </div>
    </main>
  )
}
