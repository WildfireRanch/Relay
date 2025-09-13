import Link from "next/link";
import AskEchoOpsConsole from "@/components/AskEchoOps/AskEchoOps";

export default function ControlAskOpsPage() {
  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground border-b">
        <Link href="/control" className="hover:underline">Control</Link>
        <span>/</span>
        <span className="text-foreground">Ask Ops</span>
      </div>
      <AskEchoOpsConsole />
    </div>
  );
}
