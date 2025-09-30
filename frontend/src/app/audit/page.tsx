"use client";
import { AuditPanel } from "@/components";

export default function AuditPage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">🛡️ Audit Log</h1>
      <AuditPanel />
    </main>
  );
}
