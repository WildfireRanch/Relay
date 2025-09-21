# How to Query the KB
Use /kb/search?query=<term>&k=5 with X-API-Key. Expect 200 JSON with {count, results}.
If empty: reindex via POST /docs/refresh_kb?wait=true, then retry.
