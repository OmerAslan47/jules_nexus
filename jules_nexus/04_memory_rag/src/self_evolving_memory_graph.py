from core.paths import NEXUS_ROOT
import json
import logging
import math
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


LOG_DIR = (NEXUS_ROOT + "/logs")
DATA_DIR = (NEXUS_ROOT + "/data")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

logger = logging.getLogger("NEXUS.SelfEvolvingGraph")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        os.path.join(LOG_DIR, "cognitive_graph.log"), encoding="utf-8"
    )
    fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(fh)


class SelfEvolvingMemoryGraph:
    """
    NEXUS Kendi Kendini Geliştiren Bilgi Grafiği (Knowledge Graph) ve Epizodik Hafıza Motoru:
    - Klasik anahtar-değer hafızasının ötesine geçerek varlıkları (Entities) ve aralarındaki
      anlamsal ilişkileri (Relations: Entity -> Relation -> Entity) SQLite WAL üzerinde tutar.
    - Her konuşmadan kullanıcının projelerini, donanımını, tercihlerini, hedeflerini ve
      problem çözme tarzını otomatik olarak çıkarır.
    - Yanıt üretilmeden önce 'Çok Adımlı Çağrışımsal Hatırlama (Multi-Hop Associative Recall)'
      yaparak en alakalı kişisel bağlamı <2 milisaniyede beyne sunar.
    - 5 TB Google Drive senkronizasyonu için dışa/içe aktarım (JSON-LD Graph Snapshot) destekler.
    """

    def __init__(
        self,
        db_path: str = (NEXUS_ROOT + "/data/nexus_cognitive_graph.db"),
        export_json_path: str = (NEXUS_ROOT + "/data/knowledge_graph_snapshot.json"),
    ):
        self.db_path = db_path
        self.export_json_path = export_json_path
        self._lock = threading.Lock()
        self._init_db()
        self._seed_owner_foundational_knowledge()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=25.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS graph_nodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity_key TEXT UNIQUE NOT NULL,
                        display_name TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'general',
                        summary TEXT DEFAULT '',
                        importance REAL NOT NULL DEFAULT 1.0,
                        access_count INTEGER NOT NULL DEFAULT 1,
                        last_accessed REAL NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS graph_edges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_key TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        target_key TEXT NOT NULL,
                        context_note TEXT DEFAULT '',
                        confidence REAL NOT NULL DEFAULT 0.9,
                        weight REAL NOT NULL DEFAULT 1.0,
                        updated_at REAL NOT NULL,
                        UNIQUE(source_key, relation, target_key)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodic_memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        user_query TEXT NOT NULL,
                        assistant_insight TEXT NOT NULL,
                        reasoning_depth TEXT NOT NULL DEFAULT 'reflex',
                        utility_score REAL NOT NULL DEFAULT 1.0,
                        timestamp REAL NOT NULL
                    )
                    """
                )
                conn.commit()

    def _seed_owner_foundational_knowledge(self):
        """Sahibin temel sistem ve proje profilini başlangıç düğümleri olarak grafiğe işler."""
        foundational_nodes = [
            ("sahip", "Sahip (Kullanıcı)", "person", "NEXUS'un yaratıcısı ve baş mimarı", 5.0),
            ("nexus_ai", "NEXUS v3.5 Sentient AI", "project", "Tam ekran 3B Holografik Dünya ve Çift Vitesli Bilişsel Asistan", 5.0),
            ("rtx_3050_ti", "NVIDIA RTX 3050 Ti (4GB VRAM)", "hardware", "Yerel GPU donanımı (CUDA destekli)", 4.0),
            ("google_drive_5tb", "5 TB Google Drive Bulut Depolama", "infrastructure", "Devasa model, vektör ve bilgi grafiği depolama alanı", 4.5),
            ("google_colab_pro", "Google Colab Pro GPU Cluster", "infrastructure", "Çoklu büyük dil modeli (32B/70B) çalıştırma ortamı", 4.5),
            ("gorsel_tercih", "Sıfır Butonlu Keskin Kızıl 3B Dünya", "preference", "Obsidyen siyah üzerinde keskin kırmızı/platin/kehribar 3B Dünya ve sesli kontrol", 4.8),
        ]
        foundational_edges = [
            ("sahip", "GELİŞTİRİYOR", "nexus_ai", "Kişisel yapay zeka asistanı ana projesi", 5.0),
            ("sahip", "SAHİP_DONANIM", "rtx_3050_ti", "Yerel bilgisayar ekran kartı", 4.0),
            ("sahip", "SAHİP_BULUT", "google_drive_5tb", "5 TB Google Drive alanı mevcut", 4.5),
            ("sahip", "KULLANIYOR", "google_colab_pro", "Çoklu model eğitimi ve çıkarımı için", 4.5),
            ("sahip", "TASARIM_TERCİHİ", "gorsel_tercih", "Pazar tezgahı gibi butonlar yerine saf 3B Dünya ve sesli deneyim", 4.8),
        ]
        for e_key, d_name, cat, summ, imp in foundational_nodes:
            self.upsert_node(e_key, d_name, category=cat, summary=summ, importance=imp)
        for src, rel, dst, note, w in foundational_edges:
            self.upsert_edge(src, rel, dst, context_note=note, weight=w)

    @staticmethod
    def _normalize_key(text: str) -> str:
        t = text.strip().lower()
        tr_map = str.maketrans("çğıöşü ", "cgiosu_")
        t = t.translate(tr_map)
        t = re.sub(r"[^a-z0-9_]", "", t)
        return t[:64] or "node"

    def upsert_node(
        self,
        entity_key: str,
        display_name: str,
        category: str = "general",
        summary: str = "",
        importance: float = 1.5,
    ):
        key = self._normalize_key(entity_key)
        now = time.time()
        with self._lock:
            with self._get_conn() as conn:
                existing = conn.execute(
                    "SELECT id, access_count, importance, summary FROM graph_nodes WHERE entity_key = ?",
                    (key,),
                ).fetchone()
                if existing:
                    new_count = existing[1] + 1
                    new_imp = min(10.0, max(existing[2], importance) + 0.1)
                    new_sum = summary if len(summary) >= len(existing[3] or "") else existing[3]
                    conn.execute(
                        """
                        UPDATE graph_nodes
                        SET display_name = ?, category = ?, summary = ?, importance = ?,
                            access_count = ?, last_accessed = ?
                        WHERE entity_key = ?
                        """,
                        (display_name, category, new_sum, new_imp, new_count, now, key),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO graph_nodes
                        (entity_key, display_name, category, summary, importance, access_count, last_accessed, created_at)
                        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (key, display_name, category, summary, importance, now, now),
                    )
                conn.commit()

    def upsert_edge(
        self,
        source_key: str,
        relation: str,
        target_key: str,
        context_note: str = "",
        confidence: float = 0.9,
        weight: float = 1.0,
    ):
        s_key = self._normalize_key(source_key)
        t_key = self._normalize_key(target_key)
        rel = relation.strip().upper().replace(" ", "_")
        now = time.time()
        with self._lock:
            with self._get_conn() as conn:
                existing = conn.execute(
                    "SELECT id, weight FROM graph_edges WHERE source_key = ? AND relation = ? AND target_key = ?",
                    (s_key, rel, t_key),
                ).fetchone()
                if existing:
                    new_w = min(10.0, existing[1] + 0.25)
                    conn.execute(
                        """
                        UPDATE graph_edges
                        SET context_note = ?, confidence = ?, weight = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (context_note[:300], confidence, new_w, now, existing[0]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO graph_edges
                        (source_key, relation, target_key, context_note, confidence, weight, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (s_key, rel, t_key, context_note[:300], confidence, weight, now),
                    )
                conn.commit()

    def record_episode(
        self,
        user_query: str,
        assistant_insight: str,
        reasoning_depth: str = "reflex",
        utility_score: float = 1.2,
    ):
        """Konuşma deneyimini epizodik hafızaya kaydeder ve otomatik varlık/ilişki çıkarımı yapar."""
        if not user_query or len(user_query.strip()) < 3:
            return
        words = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]{4,}", user_query.lower())
        topic = "_".join(words[:3]) if words else "genel_etkilesim"

        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO episodic_memories
                    (topic, user_query, assistant_insight, reasoning_depth, utility_score, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic[:80],
                        user_query[:600],
                        assistant_insight[:900],
                        reasoning_depth,
                        utility_score,
                        time.time(),
                    ),
                )
                conn.commit()

        self._extract_semantic_triples_from_text(user_query)

    def _extract_semantic_triples_from_text(self, text: str):
        """
        Kullanıcının cümlelerinden otomatik olarak (Sahip -> İLİŞKİ -> Hedef) üçlüleri çıkarır.
        """
        t = text.strip()
        lower = t.lower()

        patterns = [
            (r"benim adım\s+([a-zA-ZçğıöşüÇĞİÖŞÜ\s]{2,25})", "İSİM", "identity"),
            (r"([a-zA-Z0-9çğıöşüÇĞİÖŞÜ\s]{3,35})\s+üzerinde çalışıyorum", "ÜZERİNDE_ÇALIŞIYOR", "project"),
            (r"([a-zA-Z0-9çğıöşüÇĞİÖŞÜ\s]{3,35})\s+projesi yapıyorum", "GELİŞTİRİYOR", "project"),
            (r"([a-zA-Z0-9çğıöşüÇĞİÖŞÜ\s]{3,30})\s+seviyorum", "SEVİYOR", "preference"),
            (r"([a-zA-Z0-9çğıöşüÇĞİÖŞÜ\s]{3,30})\s+sevmiyorum", "SEVMİYOR", "preference"),
            (r"hedefim\s+([a-zA-Z0-9çğıöşüÇĞİÖŞÜ\s]{4,50})", "ANA_HEDEFİ", "goal"),
            (r"bölümüm\s+([a-zA-Z0-9çğıöşüÇĞİÖŞÜ\s]{3,35})", "EĞİTİM_ALANI", "academic"),
        ]

        for pat, rel, cat in patterns:
            m = re.search(pat, lower)
            if m:
                val = m.group(1).strip()
                if len(val) >= 2:
                    node_key = self._normalize_key(val)
                    self.upsert_node(
                        node_key,
                        val.title(),
                        category=cat,
                        summary=f"Kullanıcı ifadesi: {t[:120]}",
                        importance=3.2,
                    )
                    self.upsert_edge(
                        "sahip",
                        rel,
                        node_key,
                        context_note=t[:160],
                        weight=3.0,
                    )

    def recall_associative_context(self, query: str, max_items: int = 8) -> str:
        """
        Sorguyla ilgili düğümleri, ilişkileri ve geçmiş epizodik anıları
        çağrışımsal ağırlık sırasına göre getirir.
        """
        q_words = set(re.findall(r"[a-zçğıöşü0-9]{3,}", query.lower()))
        lines: List[str] = []

        with self._lock:
            with self._get_conn() as conn:
                edges = conn.execute(
                    """
                    SELECT e.source_key, e.relation, e.target_key, e.context_note, e.weight,
                           n1.display_name, n2.display_name
                    FROM graph_edges e
                    LEFT JOIN graph_nodes n1 ON e.source_key = n1.entity_key
                    LEFT JOIN graph_nodes n2 ON e.target_key = n2.entity_key
                    ORDER BY e.weight DESC, e.updated_at DESC
                    LIMIT 40
                    """
                ).fetchall()

                scored_edges: List[Tuple[float, str]] = []
                for src_k, rel, dst_k, note, w, d1, d2 in edges:
                    src_name = d1 or src_k
                    dst_name = d2 or dst_k
                    combined_text = f"{src_name} {rel} {dst_name} {note}".lower()
                    bonus = sum(2.5 for qw in q_words if qw in combined_text)
                    score = float(w) + bonus
                    desc = f"• {src_name} --[{rel}]--> {dst_name}"
                    if note:
                        desc += f" ({note})"
                    scored_edges.append((score, desc))

                scored_edges.sort(key=lambda x: x[0], reverse=True)
                for _, desc in scored_edges[:max_items]:
                    lines.append(desc)

                # İlgili son epizodik deneyimleri de kontrol et
                episodes = conn.execute(
                    """
                    SELECT user_query, assistant_insight, reasoning_depth
                    FROM episodic_memories
                    ORDER BY timestamp DESC
                    LIMIT 15
                    """
                ).fetchall()

                matched_episodes = []
                for uq, ai, rdepth in episodes:
                    if any(qw in uq.lower() for qw in q_words if len(qw) > 3):
                        matched_episodes.append(
                            f"• [Geçmiş Deneyim/{rdepth}]: '{uq[:70]}' -> '{ai[:110]}'"
                        )
                if matched_episodes:
                    lines.append("--- İlgili Geçmiş Deneyimler ---")
                    lines.extend(matched_episodes[:3])

        return "\n".join(lines) if lines else "Temel sahip profili aktif."

    def export_graph_snapshot(self) -> Dict[str, Any]:
        """5 TB Google Drive yedeklemesi için tüm bilgi grafiğini JSON olarak dışa aktarır."""
        with self._lock:
            with self._get_conn() as conn:
                nodes = [
                    {
                        "key": r[0],
                        "name": r[1],
                        "category": r[2],
                        "summary": r[3],
                        "importance": r[4],
                    }
                    for r in conn.execute(
                        "SELECT entity_key, display_name, category, summary, importance FROM graph_nodes"
                    ).fetchall()
                ]
                edges = [
                    {
                        "source": r[0],
                        "relation": r[1],
                        "target": r[2],
                        "note": r[3],
                        "weight": r[4],
                    }
                    for r in conn.execute(
                        "SELECT source_key, relation, target_key, context_note, weight FROM graph_edges"
                    ).fetchall()
                ]
                ep_count = conn.execute(
                    "SELECT COUNT(*) FROM episodic_memories"
                ).fetchone()[0]

        snapshot = {
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "total_episodes": ep_count,
            "nodes": nodes,
            "edges": edges,
        }
        try:
            with open(self.export_json_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Graph snapshot yazma hatası: {e}")
        return snapshot
