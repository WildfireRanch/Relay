"use client";
import ActionQueuePanel from "@/components/ActionQueue/ActionQueuePanel";

export default function ActionQueuePage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">📋 Action Queue</h1>
      <ActionQueuePanel />
    </main>
  );
}
