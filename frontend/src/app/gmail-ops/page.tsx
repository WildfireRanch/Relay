import GmailOpsPanel from "@/components/GmailOps/GmailOpsPanel";

export default function GmailOpsPage() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-bold mb-4">✉️ Gmail Ops</h1>
      {/* Renders the GmailOpsPanel component which handles Gmail operations UI */}
      <GmailOpsPanel />
    </main>
  );
}
