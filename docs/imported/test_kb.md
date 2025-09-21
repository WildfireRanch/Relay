\---  
title: "ASK\_ECHO KB — Test Fixture"  
tags: \[kb, test, tarana, cambium, context\]  
updated: 2025-09-21  
\---

\# Relay / ASK\_ECHO — KB Test Page

This is a \*\*test document\*\* to validate indexing, reindexing, and semantic search.  
It intentionally contains key terms and short, distinct sections.

\#\# Tarana Migration Playbook (condensed)

\- Preferred path: \*\*Tarana\*\* over \*\*Cambium\*\* when viable (capacity & SINR allow).  
\- Customer speed rule-of-thumb: Cambium tops \~100 Mbps; Tarana routinely delivers \*\*200–500 Mbps\*\*.  
\- Same-tower constraint may hide options; consider \*\*cross-tower\*\* Tarana candidates.

\> Golden metric: minimize \*install time\* and maximize \*link quality\* (SINR, RSRP).

\#\# Cambium Cleanup

\- Retire Cambium APs where \*\*co-located Tarana\*\* exists and coverage is equal/better.  
\- Keep Cambium when: rural edge cases, backhaul limitations, or licensed-band needs.

\#\# ContextEngine Sanity

ContextEngine builds deterministic context from KB hits:  
1\. retrieve → 2\. normalize → 3\. rank → 4\. concatenate.

\`\`\`json  
{  
  "engine": "ContextEngine",  
  "version": "test",  
  "steps": \["retrieve","normalize","rank","concat"\]  
}

