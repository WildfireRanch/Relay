// File: frontend/src/app/status/page.tsx

import StatusPanel from "@/components/StatusPanel";

export default function StatusPage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">📊 System Status</h1>
      <StatusPanel />
    </main>
  );
}
