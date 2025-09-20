// ─── Ops Console (Client Boundary) ───────────────────────────────────────────
"use client"

import dynamic from "next/dynamic"

// Important: ReactFlow and similar libs require a client boundary to avoid SSR
// hydration issues. We place the dynamic import here (client component) with
// `{ ssr: false }` so the server page can remain a Server Component.
const AskEchoOpsConsole = dynamic(
  () => import("@/components/AskEchoOps/AskEchoOps"),
  { ssr: false }
)

export default function OpsClient() {
  return <AskEchoOpsConsole />
}

