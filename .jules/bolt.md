## 2025-10-28 - BM25 RAG Document Ranking Optimization
**Learning:** In python-based BM25 RAG search over document chunks, pre-computing token sets per document chunk and applying `(st & unique_q_toks)` set intersection filtering reduces evaluation candidates early. Precomputing IDF values once per query eliminates repetitive `math.log` calls inside the inner loop, yielding a ~1.7x (~40%) latency improvement.
**Action:** When performing full-text search / TF-IDF / BM25 over document collections in Python, precompute static query terms and set intersections before scoring document bodies.
