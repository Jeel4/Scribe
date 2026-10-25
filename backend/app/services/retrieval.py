"""Sentence-level retrieval over all analysed meetings.

* Semantic: all-MiniLM-L6-v2 sentence embeddings (L2-normalised) in a FAISS
  IndexFlatIP, i.e. cosine similarity — the notebook's approach.
* Lexical: TF-IDF + cosine similarity — the notebook's baseline. The
  vectoriser is fitted on the indexed sentences and cached (the notebook
  refitted it on corpus + query for every query; the cached version gives
  nearly identical rankings and is much faster).

Embeddings are stored in SQLite, so indexes are rebuilt from the database
(without re-encoding) whenever a meeting is added, re-analysed or deleted.
Any change marks the index dirty and the next search rebuilds it, so
deleted meetings can never appear in results.
"""
import threading

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..db import connect


class SemanticUnavailable(RuntimeError):
    pass


def encode(embedder, texts, show_progress=False):
    vecs = embedder.encode(
        list(texts), convert_to_numpy=True, normalize_embeddings=True,
        show_progress_bar=show_progress, batch_size=64,
    )
    return np.asarray(vecs, dtype="float32")


class RetrievalIndex:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._dirty = True
        self._rows = []           # [(meeting_id, idx, speaker, text)]
        self._faiss = None
        self._faiss_rows = []     # rows that have an embedding, aligned with FAISS ids
        self._vectors = None
        self._tfidf = None
        self._tfidf_matrix = None

    def mark_dirty(self):
        with self._lock:
            self._dirty = True

    # ---------------------------------------------------------------- build
    def _rebuild(self):
        import faiss

        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT s.meeting_id, s.idx, s.speaker, s.text, s.embedding "
                "FROM sentences s JOIN meetings m ON m.id = s.meeting_id "
                "WHERE m.status = 'done' ORDER BY s.meeting_id, s.idx"
            ).fetchall()
        finally:
            conn.close()

        self._rows = [(r["meeting_id"], r["idx"], r["speaker"], r["text"]) for r in rows]

        emb_rows, vecs = [], []
        for r in rows:
            if r["embedding"] is not None:
                emb_rows.append((r["meeting_id"], r["idx"], r["speaker"], r["text"]))
                vecs.append(np.frombuffer(r["embedding"], dtype="float32"))
        self._faiss_rows = emb_rows
        if vecs:
            self._vectors = np.vstack(vecs).astype("float32")
            self._faiss = faiss.IndexFlatIP(self._vectors.shape[1])
            self._faiss.add(self._vectors)
        else:
            self._vectors, self._faiss = None, None

        texts = [r[3] for r in self._rows]
        self._tfidf, self._tfidf_matrix = None, None
        if texts:
            try:
                self._tfidf = TfidfVectorizer(stop_words="english")
                self._tfidf_matrix = self._tfidf.fit_transform(texts)
            except ValueError:  # vocabulary empty
                self._tfidf = None
        self._dirty = False

    def _ensure(self):
        if self._dirty:
            self._rebuild()

    def stats(self):
        with self._lock:
            self._ensure()
            return {
                "indexed_sentences": len(self._rows),
                "embedded_sentences": len(self._faiss_rows),
                "indexed_meetings": len({r[0] for r in self._rows}),
                "embedded_meetings": len({r[0] for r in self._faiss_rows}),
            }

    # --------------------------------------------------------------- search
    @staticmethod
    def _hit(row, score):
        return {"meeting_id": row[0], "sentence_index": row[1], "speaker": row[2],
                "text": row[3], "score": float(score)}

    def semantic(self, embedder, query, top_k=10, meeting_id=None, min_score=0.0):
        with self._lock:
            self._ensure()
            if self._faiss is None:
                raise SemanticUnavailable(
                    "No sentence embeddings are stored yet. Analyse a meeting while the "
                    "embedding model is available to enable semantic search."
                )
            q = encode(embedder, [query])
            if meeting_id is not None:
                ids = [i for i, r in enumerate(self._faiss_rows) if r[0] == meeting_id]
                if not ids:
                    return []
                scores = self._vectors[ids] @ q[0]
                order = np.argsort(scores)[::-1][:top_k]
                pairs = [(ids[i], scores[i]) for i in order]
            else:
                k = min(top_k, len(self._faiss_rows))
                scores, idxs = self._faiss.search(q, k)
                pairs = [(int(i), s) for i, s in zip(idxs[0], scores[0]) if i >= 0]
            return [self._hit(self._faiss_rows[i], s) for i, s in pairs if s >= min_score]

    def lexical(self, query, top_k=10, meeting_id=None):
        with self._lock:
            self._ensure()
            if self._tfidf is None:
                return []
            scores = cosine_similarity(self._tfidf.transform([query]), self._tfidf_matrix).ravel()
            if meeting_id is not None:
                mask = np.array([r[0] == meeting_id for r in self._rows])
                scores = np.where(mask, scores, 0.0)
            order = np.argsort(scores)[::-1][:top_k]
            return [self._hit(self._rows[i], scores[i]) for i in order if scores[i] > 0]


def add_context(conn, hits):
    """Attach the previous and next sentence and the meeting title to hits."""
    for h in hits:
        rows = conn.execute(
            "SELECT idx, speaker, text FROM sentences WHERE meeting_id=? AND idx IN (?, ?)",
            (h["meeting_id"], h["sentence_index"] - 1, h["sentence_index"] + 1),
        ).fetchall()
        ctx = {r["idx"]: {"speaker": r["speaker"], "text": r["text"]} for r in rows}
        h["before"] = ctx.get(h["sentence_index"] - 1)
        h["after"] = ctx.get(h["sentence_index"] + 1)
        title = conn.execute("SELECT title FROM meetings WHERE id=?", (h["meeting_id"],)).fetchone()
        h["meeting_title"] = title["title"] if title else None
    return hits
