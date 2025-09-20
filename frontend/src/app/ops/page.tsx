// app/ops/page.tsx
import dynamic from "next/dynamic";

export const metadata = {
  title: "Ops Console • Ask Echo",
  description: "Chat + Agentic Flow Monitor",
};

// Important: this is a client component; disable SSR to avoid ReactFlow hydration warnings.
const AskEchoOpsConsole = dynamic(
  () => import("@/components/AskEchoOps/AskEchoOps"),
  { ssr: false }
);

export default function OpsPage() {
  return (
    <div className="h-[calc(100vh-4rem)]"> {/* adjust if your header height differs */}
      <AskEchoOpsConsole />
    </div>
  );
}
