// File: frontend/src/lib/askPicking.ts
export type AskResponse = {
  final_text?: string;
  plan?: { final_answer?: string } | null;
  routed_result?: { response?: unknown; answer?: unknown } | string | null;
  critics?: unknown;
  context?: string;
  files_used?: unknown[];
  meta?: Record<string, unknown>;
};

export function pickFinalText(data: any): string {
  const d = (data?.result ?? data) as AskResponse;
  const fromRR =
    typeof d?.routed_result === "string"
      ? d.routed_result
      : (d?.routed_result as any)?.response || (d?.routed_result as any)?.answer;

  return (
    (typeof d?.final_text === "string" && d.final_text) ||
    (typeof d?.plan?.final_answer === "string" && d.plan.final_answer) ||
    (typeof fromRR === "string" && fromRR) ||
    ""
  );
}
