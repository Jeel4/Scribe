"""Runs the full analysis pipeline for one meeting and persists the results.

Pipeline (each step reuses the notebook's logic):
  1. speaker-aware sentence split (spaCy)          -> sentences, stats
  2. sentence embeddings (MiniLM)                   -> semantic search
  3. named entities (spaCy) and keywords (KeyBERT)
  4. candidate action items / decisions / risks / questions / deadlines
  5. TF-IDF extractive summary, DistilBART abstractive summary (optional)
  6. ROUGE-1/2/L F1 when a reference summary is stored

Jobs run on a single background worker thread so a long DistilBART run
does not block the web server and two jobs never compete for the CPU/GPU.
All results are written in one transaction at the end, so a failed run
never leaves half-written rows behind.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from ..db import connect, transaction
from ..models import ModelUnavailable
from . import extraction, nlp, summarization, text
from .evaluation import rouge_f1
from .retrieval import encode

log = logging.getLogger(__name__)


def _set_stage(db_path, meeting_id, stage, status="running"):
    conn = connect(db_path)
    try:
        conn.execute("UPDATE meetings SET stage=?, status=? WHERE id=?", (stage, status, meeting_id))
        conn.commit()
    finally:
        conn.close()


def run_analysis(config, registry, index, meeting_id: int, options: dict):
    db_path = config.DATABASE_PATH
    notes = []
    try:
        conn = connect(db_path)
        row = conn.execute("SELECT transcript, reference_summary FROM meetings WHERE id=?",
                           (meeting_id,)).fetchone()
        conn.close()
        if row is None:
            return  # deleted while queued
        transcript, reference = row["transcript"], (row["reference_summary"] or "").strip()

        _set_stage(db_path, meeting_id, "Splitting sentences")
        try:
            spacy_nlp = registry.spacy()
        except ModelUnavailable as exc:
            raise RuntimeError(
                f"spaCy model '{config.SPACY_MODEL}' is not installed ({exc}). "
                "Run: python -m spacy download en_core_web_sm"
            ) from exc
        sentences = text.split_sentences(spacy_nlp, transcript)
        if not sentences:
            raise RuntimeError("No sentences could be found in this transcript.")
        stats = text.basic_stats(transcript, sentences)

        _set_stage(db_path, meeting_id, "Embedding sentences")
        embeddings = None
        try:
            embeddings = encode(registry.embedder(), [s.text for s in sentences])
        except ModelUnavailable as exc:
            notes.append(f"Sentence embeddings unavailable — this meeting is searchable "
                         f"lexically only. ({exc})")

        _set_stage(db_path, meeting_id, "Extracting entities and keywords")
        entities = nlp.extract_entities(spacy_nlp, transcript)
        keywords, kw_method = nlp.extract_keywords(registry, transcript)
        if kw_method != "keybert":
            notes.append("KeyBERT unavailable — keywords come from the TF-IDF fallback.")

        _set_stage(db_path, meeting_id, "Extracting candidate items")
        items = extraction.extract_information(sentences)

        _set_stage(db_path, meeting_id, "Summarising (TF-IDF)")
        summaries = [summarization.extractive(transcript)]
        if options.get("abstractive", True):
            _set_stage(db_path, meeting_id, "Summarising (DistilBART — slow on CPU)")
            abstr = summarization.abstractive(registry, transcript)
            summaries.append(abstr)
            if abstr.status == "fallback":
                notes.append(abstr.note)

        with transaction(db_path) as conn:
            if conn.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone() is None:
                return  # deleted while running
            for table in ("sentences", "entities", "keywords", "extractions", "summaries"):
                conn.execute(f"DELETE FROM {table} WHERE meeting_id=?", (meeting_id,))
            conn.executemany(
                "INSERT INTO sentences (meeting_id, idx, speaker, text, embedding) VALUES (?,?,?,?,?)",
                [(meeting_id, s.idx, s.speaker, s.text,
                  embeddings[i].tobytes() if embeddings is not None else None)
                 for i, s in enumerate(sentences)],
            )
            conn.executemany(
                "INSERT INTO entities (meeting_id, text, label, count) VALUES (?,?,?,?)",
                [(meeting_id, e["text"], e["label"], e["count"]) for e in entities],
            )
            conn.executemany(
                "INSERT INTO keywords (meeting_id, rank, keyword, score, method) VALUES (?,?,?,?,?)",
                [(meeting_id, i, k["keyword"], k["score"], kw_method) for i, k in enumerate(keywords)],
            )
            conn.executemany(
                "INSERT INTO extractions (meeting_id, kind, text, owner, deadline, speaker, sentence_index) "
                "VALUES (?,?,?,?,?,?,?)",
                [(meeting_id, r["kind"], r["text"], r["owner"], r["deadline"], r["speaker"],
                  r["sentence_index"]) for r in items],
            )
            for s in summaries:
                scores = rouge_f1(reference, s.text) if (reference and s.status == "ok") else {}
                conn.execute(
                    "INSERT INTO summaries (meeting_id, method, status, text, note, model_name, "
                    "rouge1, rouge2, rougeL) VALUES (?,?,?,?,?,?,?,?,?)",
                    (meeting_id, s.method, s.status, s.text, s.note, s.model_name,
                     scores.get("rouge1"), scores.get("rouge2"), scores.get("rougeL")),
                )
            conn.execute(
                "UPDATE meetings SET status='done', stage=NULL, error=NULL, word_count=?, "
                "sentence_count=?, speaker_count=?, notes_json=?, analyzed_at=datetime('now') "
                "WHERE id=?",
                (stats["word_count"], stats["sentence_count"], stats["speaker_count"],
                 json.dumps(notes), meeting_id),
            )
        index.mark_dirty()
    except Exception as exc:  # noqa: BLE001 - record any failure on the meeting
        log.exception("Analysis of meeting %s failed", meeting_id)
        msg = str(exc) if isinstance(exc, RuntimeError) else f"{type(exc).__name__}: {exc}"
        conn = connect(db_path)
        try:
            conn.execute("UPDATE meetings SET status='failed', stage=NULL, error=? WHERE id=?",
                         (msg[:500], meeting_id))
            conn.commit()
        finally:
            conn.close()
        index.mark_dirty()


def rescore_meeting(conn, meeting_id: int, reference: str):
    """Recompute ROUGE for stored summaries after the reference changes."""
    reference = (reference or "").strip()
    for s in conn.execute("SELECT id, status, text FROM summaries WHERE meeting_id=?",
                          (meeting_id,)).fetchall():
        if reference and s["status"] == "ok":
            sc = rouge_f1(reference, s["text"])
            vals = (sc["rouge1"], sc["rouge2"], sc["rougeL"])
        else:
            vals = (None, None, None)
        conn.execute("UPDATE summaries SET rouge1=?, rouge2=?, rougeL=? WHERE id=?", (*vals, s["id"]))


class JobRunner:
    """One background worker; in tests (ASYNC_ANALYSIS=False) jobs run inline."""

    def __init__(self, config, registry, index):
        self.config, self.registry, self.index = config, registry, index
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scribe-analysis")

    def submit(self, meeting_id, options):
        if self.config.ASYNC_ANALYSIS:
            self._pool.submit(run_analysis, self.config, self.registry, self.index, meeting_id, options)
        else:
            run_analysis(self.config, self.registry, self.index, meeting_id, options)
