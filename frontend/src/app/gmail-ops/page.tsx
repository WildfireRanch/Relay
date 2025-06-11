// File: app/gmail-ops/page.tsx

import dynamic from "next/dynamic";
const GmailOpsPanel = dynamic(() => import("@/components/GmailOps/GmailOpsPanel"), { ssr: false });

export default function GmailOpsPage() {
  return (
    <div>
      <h1 className="font-bold text-xl mb-4">Email Ops</h1>
      <GmailOpsPanel />
    </div>
  );
}
