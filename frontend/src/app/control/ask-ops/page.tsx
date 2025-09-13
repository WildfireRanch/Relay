// File: src/app/control/ask-ops/page.tsx
"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

// Dynamically import the heavy client-only console (no SSR)
const AskEchoOpsConsole = dynamic(
  () => import("@/components/AskEchoOps/AskEchoOps"),
  { ssr: false }
);

export default function ControlAskOpsPage() {
  return (
    <div className="flex h-screen flex-col">
      {/* Breadcrumb header */}
      <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground border-b">
        <Link href="/control" className="hover:underline">
          Control
        </Link>
        <span>/</span>
        <span className="text-foreground">Ask Ops</span>
      </div>

      {/* Client-only console */}
      <AskEchoOpsConsole />
    </div>
  );
}
