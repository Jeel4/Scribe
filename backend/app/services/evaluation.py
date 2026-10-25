"""ROUGE scoring and retrieval metrics, as defined in the notebook."""
from rouge_score import rouge_scorer

_scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)


def rouge_f1(reference: str, prediction: str) -> dict:
    """ROUGE-1/2/L F1 with Porter stemming (rouge-score), as in the notebook."""
    scores = _scorer.score(str(reference), str(prediction))
    return {k: float(v.fmeasure) for k, v in scores.items()}


def retrieval_metrics(search_fn, queries, k=5):
    """Top-1 accuracy, Top-k accuracy and MRR at the meeting level.

    `queries` must be manually verified {query, gold_meeting_id} pairs —
    the notebook deliberately reports nothing without them, and so does
    this app. A hit counts when a retrieved sentence belongs to the gold
    meeting; rank is the first such position.
    """
    rows = []
    for q in queries:
        hits = search_fn(q["query"], k)
        got = [h["meeting_id"] for h in hits]
        gold = int(q["gold_meeting_id"])
        rank = next((i + 1 for i, m in enumerate(got) if m == gold), None)
        rows.append({
            "query": q["query"], "gold_meeting_id": gold,
            "top1_hit": int(bool(got) and got[0] == gold),
            "topk_hit": int(gold in got),
            "reciprocal_rank": 1.0 / rank if rank else 0.0,
        })
    n = len(rows)
    summary = {
        "evaluated_queries": n, "k": k,
        "top1_accuracy": sum(r["top1_hit"] for r in rows) / n if n else None,
        "topk_accuracy": sum(r["topk_hit"] for r in rows) / n if n else None,
        "mrr": sum(r["reciprocal_rank"] for r in rows) / n if n else None,
    }
    return summary, rows
