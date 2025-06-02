import ActionQueue from "@/components/ActionQueue/ActionQueue"

export default function ControlPage() {
  return (
    <main className="p-6">
      <h2 className="text-2xl font-bold mb-4">Queued Actions</h2>
      <ActionQueue />
    </main>
  )
}
