"""Semantic (MiniLM + FAISS) and lexical (TF-IDF) search across meetings."""
from flask import Blueprint, abort, jsonify, request

from ..models import ModelUnavailable
from ..services.retrieval import SemanticUnavailable, add_context
from .common import bad_request, cfg, db, index, parse_int, registry

bp = Blueprint("search", __name__)
MAX_QUERY = 500


def run_search(query, mode, top_k, meeting_id=None, min_score=None):
    """Shared by /search and the retrieval evaluation. Raises 503 with a
    readable message when semantic search is impossible."""
    if mode == "lexical":
        return index().lexical(query, top_k=top_k, meeting_id=meeting_id)
    try:
        embedder = registry().embedder()
    except ModelUnavailable as exc:
        abort(503, description=f"Semantic search is unavailable: the embedding model could not be "
                               f"loaded ({exc}). Lexical search still works.")
    try:
        return index().semantic(
            embedder, query, top_k=top_k, meeting_id=meeting_id,
            min_score=cfg().SEMANTIC_MIN_SCORE if min_score is None else min_score,
        )
    except SemanticUnavailable as exc:
        abort(503, description=str(exc))


@bp.get("/search")
def search():
    query = " ".join((request.args.get("q") or "").split())
    if not query:
        bad_request("Enter a search query.")
    if len(query) > MAX_QUERY:
        bad_request(f"The query is too long (max {MAX_QUERY} characters).")
    mode = request.args.get("mode", "semantic")
    if mode not in ("semantic", "lexical"):
        bad_request("'mode' must be 'semantic' or 'lexical'.")
    top_k = parse_int(request.args.get("top_k"), "top_k", 10, 1, 50)
    meeting_id = parse_int(request.args.get("meeting_id"), "meeting_id", None, 1, 10**9)

    hits = run_search(query, mode, top_k, meeting_id)
    conn = db()
    try:
        add_context(conn, hits)
    finally:
        conn.close()
    return jsonify(
        query=query, mode=mode, top_k=top_k, meeting_id=meeting_id,
        min_score=cfg().SEMANTIC_MIN_SCORE if mode == "semantic" else None,
        results=hits, index=index().stats(),
    )
