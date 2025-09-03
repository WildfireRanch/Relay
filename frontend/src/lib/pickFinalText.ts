// Order: final_text → routed_result.response/text/answer → plan.final_answer → meta.details.reply_head
export function pickFinalText(result: any): string {
  if (!result) return "";
  const ft = (result.final_text ?? "").toString().trim();
  if (ft) return ft;

  const rr = result.routed_result ?? {};
  const resp = rr.response;
  const candidates = [
    rr.text,
    rr.answer,
    (resp && typeof resp === "object" ? (resp.text || resp.content || resp.message || resp.summary) : undefined),
    resp,
  ].filter((x) => typeof x === "string" && x.trim());
  if (candidates.length) return (candidates[0] as string).trim();

  const fa = (result.plan?.final_answer ?? "").toString().trim();
  if (fa) return fa;

  const head = (result.meta?.details?.reply_head ?? result.meta?.reply_head ?? "").toString().trim();
  return head || "";
}
