// File: frontend/src/lib/pickFinalText.ts
// Purpose: Safe helper to extract the best user-facing text from a routed result or plan
// (mirrors server-side logic; no 'any')

export type RoutedResult =
  | string
  | {
      response?: unknown;
      answer?: unknown;
      [k: string]: unknown;
    }
  | null
  | undefined;

export type Plan = {
  final_answer?: unknown;
  [k: string]: unknown;
} | null | undefined;

function asString(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

export function pickFinalText(plan: Plan, routedResult: RoutedResult): string {
  if (typeof routedResult === "string") {
    const s = asString(routedResult);
    if (s) return s;
  } else if (routedResult && typeof routedResult === "object") {
    const rr = routedResult as Record<string, unknown>;
    const resp = asString(rr.response);
    if (resp) return resp;
    const ans = asString(rr.answer);
    if (ans) return ans;
  }

  if (plan && typeof plan === "object") {
    const fa = asString((plan as Record<string, unknown>).final_answer);
    if (fa) return fa;
  }

  return "";
}
