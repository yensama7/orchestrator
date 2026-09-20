-- Hybrid retrieval: BM25 + vector, fused with RRF (k=60), then rerank the top
-- 24 locally with bge-reranker-v2-m3 and keep 6 (§20.7). status='active' in
-- both branches is what stops an agent re-proposing a reversed decision.
WITH vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> $2) AS rank
  FROM semantic_memory
  WHERE tenant_id = $1 AND status = 'active'
  ORDER BY embedding <=> $2 LIMIT 50
),
kw AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS rank
  FROM semantic_memory, plainto_tsquery('english', $3) q
  WHERE tenant_id = $1 AND status = 'active' AND tsv @@ q
  LIMIT 50
)
SELECT m.*, 1.0/(60 + COALESCE(v.rank, 1000))
          + 1.0/(60 + COALESCE(k.rank, 1000)) AS rrf
FROM semantic_memory m
LEFT JOIN vec v ON v.id = m.id
LEFT JOIN kw  k ON k.id = m.id
WHERE v.id IS NOT NULL OR k.id IS NOT NULL
ORDER BY rrf DESC
LIMIT 24;
