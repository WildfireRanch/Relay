"use client";
import GmailOpsPanel from "@/components/GmailOps/GmailOpsPanel";

export default function EmailPage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">✉️ Email Ops</h1>
      <GmailOpsPanel />
    </main>
  );
}
