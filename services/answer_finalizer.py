# File: services/answer_finalizer.py
from typing import Any, Dict, Optional

def _best_string(x: Any) -> Optional[str]:
    if isinstance(x, str) and x.strip(): return x.strip()
    if isinstance(x, dict):
        for k in ("text","message","content","answer"):
            v = x.get(k)
            if isinstance(v, str) and v.strip(): return v.strip()
        ch = x.get("choices")
        if isinstance(ch, list) and ch:
            msg = (ch[0] or {}).get("message", {})
            c = msg.get("content")
            if isinstance(c, str) and c.strip(): return c.strip()
        cnt = x.get("content")
        if isinstance(cnt, list) and cnt:
            first = cnt[0] or {}
            t = first.get("text")
            if isinstance(t, str) and t.strip(): return t.strip()
    return None

def finalize(envelope: Dict[str, Any]) -> Dict[str, Any]:
    ft = envelope.get("final_text")
    if isinstance(ft, str) and ft.strip(): return envelope
    plan = envelope.get("plan") or {}
    rr   = envelope.get("routed_result") or {}
    ft = ((plan.get("final_answer") or "").strip()
          or (rr.get("answer") or "").strip()
          or _best_string(rr.get("response")) or "")
    if not ft:
        meta = envelope.get("meta") or {}
        details = meta.get("details") or {}
        head = details.get("reply_head") or meta.get("reply_head")
        if isinstance(head, str) and head.strip():
            ft = head.strip()
    envelope["final_text"] = ft
    return envelope
