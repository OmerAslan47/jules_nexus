import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from self_evolving_memory_graph import SelfEvolvingMemoryGraph
from knowledge_rag_engine import LocalKnowledgeBase, DocumentChunker, TurkishTextNormalizer


def test_self_evolving_memory_graph():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "graph_test.db")
        graph = SelfEvolvingMemoryGraph(db_path=db_path)

        graph.record_episode(
            user_query="Python optimizasyon yöntemleri nelerdir?",
            assistant_insight="Python optimizasyon için PyPy, Cython ve önbellek mekanizmaları kullanılır.",
            reasoning_depth="deep",
            utility_score=2.0
        )

        ctx = graph.recall_associative_context("Python optimizasyon", max_items=5)
        assert len(ctx) > 0

        snap = graph.export_graph_snapshot()
        assert snap["total_episodes"] >= 1


def test_local_knowledge_base():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "rag_test.db")
        doc_file = os.path.join(tmp_dir, "nexus_doc.txt")
        with open(doc_file, "w", encoding="utf-8") as f:
            f.write("NEXUS, 3 katmanlı hibrit beyin ve akıllı araç seçiciye sahiptir.")

        kb = LocalKnowledgeBase(db_path=db_path)

        res = kb.index_single_file(doc_file, force=True)
        assert res.get("status") in ["success", "indexed"] or res.get("chunks", 0) > 0

        results = kb.query_knowledge_base("NEXUS beyin", top_k=3)
        assert len(results) > 0
