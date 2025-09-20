// ─── Ops Page (Server Component) ─────────────────────────────────────────────
// Renders a client boundary to host interactive console (no SSR for ReactFlow).
import OpsClient from "./OpsClient";

export const metadata = {
  title: "Ops Console • Ask Echo",
  description: "Chat + Agentic Flow Monitor",
};

export default function OpsPage() {
  return (
    <div className="h-[calc(100vh-4rem)]"> {/* adjust if your header height differs */}
      <OpsClient />
    </div>
  );
}
