"use client";
import LogsPanel from "@/components/LogsPanel/LogsPanel";

export default function LogsPage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">📜 Logs</h1>
      <LogsPanel />
    </main>
  );
}
