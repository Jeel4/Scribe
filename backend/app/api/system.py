"""Health, model status and dashboard statistics."""
from flask import Blueprint, jsonify

from ..services.extraction import KINDS
from .common import cfg, db, index, registry

bp = Blueprint("system", __name__)


@bp.get("/health")
def health():
    conn = db()
    try:
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    finally:
        conn.close()
    c = cfg()
    return jsonify(
        status="ok" if db_ok else "degraded",
        database=db_ok,
        models=registry().status(),
        index=index().stats(),
        limits={"max_upload_mb": c.MAX_UPLOAD_MB, "min_transcript_words": c.MIN_TRANSCRIPT_WORDS,
                "semantic_min_score": c.SEMANTIC_MIN_SCORE},
    )


@bp.post("/models/retry")
def retry_models():
    """Forget earlier load failures and try loading every model again
    (e.g. after fixing the network or installing a missing package)."""
    reg = registry()
    reg.retry_failed()
    reg.preload()
    return jsonify(models=reg.status())


@bp.get("/dashboard")
def dashboard():
    conn = db()
    try:
        by_status = {r["status"]: r["n"] for r in
                     conn.execute("SELECT status, COUNT(*) n FROM meetings GROUP BY status")}
        words = conn.execute("SELECT COALESCE(SUM(word_count),0) FROM meetings WHERE status='done'").fetchone()[0]
        kinds = {r["kind"]: r["n"] for r in
                 conn.execute("SELECT kind, COUNT(*) n FROM extractions GROUP BY kind")}
        recent = [dict(r) for r in conn.execute(
            "SELECT id, title, status, source, word_count, created_at FROM meetings "
            "ORDER BY created_at DESC, id DESC LIMIT 6")]
        open_actions = [dict(r) for r in conn.execute(
            "SELECT e.meeting_id, m.title AS meeting_title, e.text, e.owner, e.deadline "
            "FROM extractions e JOIN meetings m ON m.id = e.meeting_id "
            "WHERE e.kind='action' ORDER BY m.created_at DESC, e.sentence_index LIMIT 8")]
    finally:
        conn.close()
    return jsonify(
        meetings={"total": sum(by_status.values()), **{s: by_status.get(s, 0)
                  for s in ("pending", "running", "done", "failed")}},
        analysed_words=words,
        extraction_totals={k: kinds.get(k, 0) for k in KINDS},
        recent=recent,
        recent_actions=open_actions,
        index=index().stats(),
        models=registry().status(),
    )
