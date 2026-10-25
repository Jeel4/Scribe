"""Evaluation endpoints.

Only metrics that can be computed honestly are returned:
* ROUGE-1/2/L F1 for meetings that have a human reference summary;
* corpus statistics and extraction counts (counts, not accuracy — there is
  no ground truth for action items, so precision/recall is not reported);
* retrieval Top-1 / Top-k / MRR only for query→meeting pairs the user
  supplies and has verified by hand.
"""
from flask import Blueprint, jsonify, request

from ..services.evaluation import retrieval_metrics
from ..services.extraction import KINDS
from .common import bad_request, db, parse_int
from .search import MAX_QUERY, run_search

bp = Blueprint("evaluation", __name__)
METHODS = ("tfidf", "distilbart")


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


@bp.get("/evaluation")
def evaluation():
    conn = db()
    try:
        meetings = conn.execute(
            "SELECT id, title, source, word_count, sentence_count, speaker_count, "
            "reference_summary IS NOT NULL AS has_reference FROM meetings WHERE status='done' "
            "ORDER BY id"
        ).fetchall()
        summaries = {}
        for s in conn.execute("SELECT meeting_id, method, status, text, rouge1, rouge2, rougeL FROM summaries"):
            summaries.setdefault(s["meeting_id"], {})[s["method"]] = s
        counts = {}
        for c in conn.execute("SELECT meeting_id, kind, COUNT(*) n FROM extractions GROUP BY meeting_id, kind"):
            counts.setdefault(c["meeting_id"], {})[c["kind"]] = c["n"]
    finally:
        conn.close()

    rows, identical = [], 0
    for m in meetings:
        sm = summaries.get(m["id"], {})
        row = {
            "meeting_id": m["id"], "title": m["title"], "source": m["source"],
            "word_count": m["word_count"], "sentence_count": m["sentence_count"],
            "speaker_count": m["speaker_count"], "has_reference": bool(m["has_reference"]),
            "extraction_counts": {k: counts.get(m["id"], {}).get(k, 0) for k in KINDS},
            "summaries": {},
        }
        for method in METHODS:
            s = sm.get(method)
            row["summaries"][method] = None if s is None else {
                "status": s["status"],
                "words": len((s["text"] or "").split()),
                "rouge": None if s["rouge1"] is None else
                {"rouge1": s["rouge1"], "rouge2": s["rouge2"], "rougeL": s["rougeL"]},
            }
        # Sanity check for the notebook bug: both "methods" producing the same text.
        t, d = sm.get("tfidf"), sm.get("distilbart")
        row["summaries_identical"] = bool(t and d and d["status"] == "ok" and t["text"] == d["text"])
        identical += row["summaries_identical"]
        rows.append(row)

    rouge = {}
    for method in METHODS:
        scored = [r["summaries"][method]["rouge"] for r in rows
                  if r["summaries"][method] and r["summaries"][method]["rouge"]]
        rouge[method] = {
            "meetings": len(scored),
            **{k: _mean([s[k] for s in scored]) for k in ("rouge1", "rouge2", "rougeL")},
        }
    # Paired comparison: only meetings where BOTH methods have real scores.
    paired = [r for r in rows if all(r["summaries"][m] and r["summaries"][m]["rouge"] for m in METHODS)]
    rouge_paired = {
        "meetings": len(paired),
        **{m: {k: _mean([r["summaries"][m]["rouge"][k] for r in paired])
               for k in ("rouge1", "rouge2", "rougeL")} for m in METHODS},
    }
    fallbacks = sum(1 for r in rows if r["summaries"]["distilbart"]
                    and r["summaries"]["distilbart"]["status"] == "fallback")

    totals = {k: sum(r["extraction_counts"][k] for r in rows) for k in KINDS}
    return jsonify(
        meetings=rows,
        corpus={
            "analysed_meetings": len(rows),
            "with_reference": sum(r["has_reference"] for r in rows),
            "avg_words": _mean([r["word_count"] for r in rows]),
            "avg_sentences": _mean([r["sentence_count"] for r in rows]),
            "extraction_totals": totals,
            "distilbart_fallbacks": fallbacks,
            "identical_summary_pairs": identical,
        },
        rouge=rouge,
        rouge_paired=rouge_paired,
    )


@bp.post("/evaluation/retrieval")
def evaluate_retrieval():
    """Body: {"mode": "semantic"|"lexical", "k": 5,
              "queries": [{"query": "...", "gold_meeting_id": 3}, ...]}"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        bad_request("Send a JSON body with a 'queries' list.")
    mode = body.get("mode", "semantic")
    if mode not in ("semantic", "lexical"):
        bad_request("'mode' must be 'semantic' or 'lexical'.")
    k = parse_int(body.get("k"), "k", 5, 1, 50)
    queries = body.get("queries")
    if not isinstance(queries, list) or not queries:
        bad_request("'queries' must be a non-empty list of {query, gold_meeting_id} pairs.")
    if len(queries) > 200:
        bad_request("At most 200 queries per evaluation.")

    conn = db()
    try:
        valid_ids = {r[0] for r in conn.execute("SELECT id FROM meetings WHERE status='done'")}
    finally:
        conn.close()
    clean = []
    for i, q in enumerate(queries, 1):
        if not isinstance(q, dict):
            bad_request(f"Query #{i} must be an object.")
        text = " ".join(str(q.get("query", "")).split())
        if not text or len(text) > MAX_QUERY:
            bad_request(f"Query #{i} is empty or too long.")
        try:
            gold = int(q.get("gold_meeting_id"))
        except (TypeError, ValueError):
            bad_request(f"Query #{i} needs a numeric gold_meeting_id.")
        if gold not in valid_ids:
            bad_request(f"Query #{i}: meeting {gold} does not exist or has not been analysed.")
        clean.append({"query": text, "gold_meeting_id": gold})

    # min_score=0 so the metric reflects pure ranking, not the display threshold.
    summary, rows = retrieval_metrics(
        lambda q, kk: run_search(q, mode, kk, min_score=0.0), clean, k=k)
    return jsonify(mode=mode, summary=summary, rows=rows)
