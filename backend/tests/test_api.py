"""End-to-end tests through the Flask test client (real spaCy, TF-IDF,
ROUGE and FAISS; fake embedder; DistilBART/KeyBERT unavailable)."""
import io

from conftest import _make_app, sample_text, upload

PLATFORM = "synthetic_platform_migration.txt"
REMOTE = "synthetic_remote_control_design.txt"
STANDUP = "synthetic_weekly_standup.txt"


def load_sample(client, name):
    r = client.post(f"/api/samples/{name}", json={})
    assert r.status_code == 202, r.get_json()
    return r.get_json()["id"]


# ------------------------------------------------------------- validation
def test_upload_validation(client, app):
    assert client.post("/api/meetings", data={}).status_code == 400
    r = upload(client, "hello " * 50, filename="notes.pdf")
    assert r.status_code == 400 and ".txt" in r.get_json()["error"]
    r = upload(client, "   \n ", filename="empty.txt")
    assert r.status_code == 400 and "empty" in r.get_json()["error"]
    r = upload(client, b"\x00\x01\x02binary" * 20, filename="bin.txt")
    assert r.status_code == 400 and "binary" in r.get_json()["error"]
    r = upload(client, "caf\xe9 ".encode("latin-1") * 40, filename="latin.txt")
    assert r.status_code == 400 and "UTF-8" in r.get_json()["error"]
    r = upload(client, "too short", filename="short.txt")
    assert r.status_code == 400 and "words" in r.get_json()["error"]
    limit = int(app.extensions["scribe.config"].MAX_UPLOAD_MB * 1024 * 1024)
    r = upload(client, "word " * (limit // 5 + 10), filename="big.txt")
    assert r.status_code == 413 and "too large" in r.get_json()["error"]
    # Nothing was stored by the rejected uploads.
    assert client.get("/api/meetings").get_json()["meetings"] == []


def test_errors_are_json_without_tracebacks(app):
    @app.get("/api/_boom")
    def boom():
        raise ValueError("secret internal detail")

    client = app.test_client()
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.is_json
    assert client.get("/api/meetings/999").status_code == 404
    r = client.get("/api/_boom")
    assert r.status_code == 500
    body = r.get_data(as_text=True)
    assert "secret internal detail" not in body and "Traceback" not in body


# --------------------------------------------------------------- analysis
def test_upload_and_full_analysis(client):
    r = upload(client, sample_text(STANDUP), filename="standup.txt", title="Standup",
               abstractive="false")
    assert r.status_code == 202
    mid = r.get_json()["id"]
    m = client.get(f"/api/meetings/{mid}").get_json()
    assert m["status"] == "done", m["error"]
    assert m["title"] == "Standup"
    assert m["speaker_count"] == 3 and m["sentence_count"] > 10
    assert m["summaries"]["tfidf"]["status"] == "ok"
    assert "distilbart" not in m["summaries"]  # abstractive was switched off
    assert m["summaries"]["tfidf"]["rouge"] is None  # no reference -> no ROUGE
    assert m["keyword_method"] == "tfidf_fallback"
    assert any("KeyBERT unavailable" in n for n in m["notes"])
    assert m["embedded"] is True
    assert all(s["speaker"] for s in m["sentences"])


def test_distilbart_fallback_is_labelled_and_not_scored(client):
    mid = load_sample(client, PLATFORM)
    m = client.get(f"/api/meetings/{mid}").get_json()
    assert m["status"] == "done", m["error"]
    assert m["has_reference"] and m["source"] == "sample"
    assert m["title"].startswith("[Synthetic sample]")
    d, t = m["summaries"]["distilbart"], m["summaries"]["tfidf"]
    assert d["status"] == "fallback"
    assert "NOT a DistilBART output" in d["note"]
    assert d["rouge"] is None            # fallback text is never scored as DistilBART
    assert t["status"] == "ok" and t["rouge"] is not None
    assert 0 < t["rouge"]["rouge1"] <= 1
    ev = client.get("/api/evaluation").get_json()
    assert ev["rouge"]["distilbart"]["meetings"] == 0
    assert ev["rouge"]["tfidf"]["meetings"] == 1
    assert ev["corpus"]["distilbart_fallbacks"] == 1
    assert ev["corpus"]["identical_summary_pairs"] == 0


def test_extraction_on_platform_sample(client):
    mid = load_sample(client, PLATFORM)
    ex = client.get(f"/api/meetings/{mid}").get_json()["extractions"]
    webhook = [a for a in ex["action"] if "webhook endpoints" in a["text"]]
    assert webhook and webhook[0]["owner"] == "Daniel" and "Friday" in webhook[0]["deadline"]
    assert any("decided to do the cut-over" in d["text"] for d in ex["decision"])
    assert any("blocked" in r["text"] for r in ex["risk"])
    assert any(q["text"].endswith("?") for q in ex["question"])
    assert all(a["owner"] not in {"We", "I", "It"} for a in ex["action"])


def test_ami_style_speaker_tags(client):
    mid = load_sample(client, REMOTE)
    m = client.get(f"/api/meetings/{mid}").get_json()
    assert m["speaker_count"] == 4
    assert {s["speaker"] for s in m["sentences"]} == {"A", "B", "C", "D"}
    # "[C] I will make a cost calculation..." -> owner is speaker C
    cost = [a for a in m["extractions"]["action"] if "cost calculation" in a["text"]]
    assert cost and cost[0]["owner"] == "C"
    # speaker tags are not reported as entities
    assert not any(e["text"] in {"[A]", "A", "[B]"} for e in m["entities"])


def test_reference_update_recomputes_rouge(client):
    mid = load_sample(client, STANDUP)
    m = client.get(f"/api/meetings/{mid}").get_json()
    assert m["summaries"]["tfidf"]["rouge"] is None
    ref = "Tom finished the search filters. Aisha is fixing the PDF export bug and renews the certificate by Friday."
    m = client.put(f"/api/meetings/{mid}/reference", json={"reference_summary": ref}).get_json()
    assert m["has_reference"] and m["summaries"]["tfidf"]["rouge"]["rouge1"] > 0
    m = client.put(f"/api/meetings/{mid}/reference", json={"reference_summary": ""}).get_json()
    assert not m["has_reference"] and m["summaries"]["tfidf"]["rouge"] is None
    assert client.put(f"/api/meetings/{mid}/reference", json={}).status_code == 400


# ----------------------------------------------------------------- search
def test_search_modes_context_and_no_stale_results(client):
    a = load_sample(client, PLATFORM)
    b = load_sample(client, REMOTE)

    r = client.get("/api/search?q=payment webhook&mode=lexical").get_json()
    assert r["results"] and r["results"][0]["meeting_id"] == a
    top = r["results"][0]
    assert "meeting_title" in top and "before" in top and "after" in top

    r = client.get("/api/search?q=battery case plastic&mode=semantic&top_k=5").get_json()
    assert r["results"] and r["results"][0]["meeting_id"] == b
    assert all(h["score"] >= r["min_score"] for h in r["results"])

    # Filter to one meeting
    r = client.get(f"/api/search?q=budget&mode=lexical&meeting_id={a}").get_json()
    assert all(h["meeting_id"] == a for h in r["results"])

    # Delete meeting b: none of its sentences may come back, in either mode.
    assert client.delete(f"/api/meetings/{b}").status_code == 200
    for mode in ("semantic", "lexical"):
        r = client.get(f"/api/search?q=battery case plastic remote&mode={mode}&top_k=50").get_json()
        assert all(h["meeting_id"] != b for h in r["results"]), mode
    assert client.get(f"/api/meetings/{b}").status_code == 404

    # Adding a meeting makes it searchable immediately.
    c = load_sample(client, STANDUP)
    # (The fake embedder is a bag-of-words hash, so only check membership.)
    r = client.get("/api/search?q=staging server certificate expires&mode=semantic&top_k=5").get_json()
    assert c in {h["meeting_id"] for h in r["results"]}
    r = client.get("/api/search?q=certificate expires&mode=lexical").get_json()
    assert r["results"][0]["meeting_id"] == c


def test_search_validation(client):
    assert client.get("/api/search?q=").status_code == 400
    assert client.get("/api/search?q=x&mode=fuzzy").status_code == 400
    assert client.get("/api/search?q=x&top_k=0").status_code == 400
    assert client.get("/api/search?q=" + "a" * 600).status_code == 400
    # empty corpus: lexical returns an empty list, semantic explains why
    assert client.get("/api/search?q=hello&mode=lexical").get_json()["results"] == []
    r = client.get("/api/search?q=hello&mode=semantic")
    assert r.status_code == 503 and "embeddings" in r.get_json()["error"]


def test_semantic_unavailable_without_embedder(tmp_path):
    app = _make_app(tmp_path, embedder=False)
    client = app.test_client()
    mid = load_sample(client, STANDUP)
    m = client.get(f"/api/meetings/{mid}").get_json()
    assert m["status"] == "done" and m["embedded"] is False
    assert any("lexically only" in n for n in m["notes"])
    r = client.get("/api/search?q=certificate&mode=semantic")
    assert r.status_code == 503 and "Lexical search still works" in r.get_json()["error"]
    assert client.get("/api/search?q=certificate&mode=lexical").get_json()["results"]


def test_retrieval_evaluation_requires_gold_pairs(client):
    a = load_sample(client, PLATFORM)
    b = load_sample(client, REMOTE)
    assert client.post("/api/evaluation/retrieval", json={"queries": []}).status_code == 400
    assert client.post("/api/evaluation/retrieval",
                       json={"queries": [{"query": "x", "gold_meeting_id": 999}]}).status_code == 400
    body = {"mode": "lexical", "k": 3, "queries": [
        {"query": "payment provider webhooks", "gold_meeting_id": a},
        {"query": "infrared chip push buttons", "gold_meeting_id": b},
        {"query": "infrared chip push buttons", "gold_meeting_id": a},  # deliberately wrong gold
    ]}
    r = client.post("/api/evaluation/retrieval", json=body).get_json()
    s = r["summary"]
    assert s["evaluated_queries"] == 3
    assert abs(s["top1_accuracy"] - 2 / 3) < 1e-9
    assert [row["top1_hit"] for row in r["rows"]] == [1, 1, 0]


def test_reanalyze_and_dashboard(client):
    mid = load_sample(client, STANDUP)
    r = client.post(f"/api/meetings/{mid}/analyze", json={"abstractive": True})
    assert r.status_code == 202
    m = client.get(f"/api/meetings/{mid}").get_json()
    assert m["status"] == "done" and m["summaries"]["distilbart"]["status"] == "fallback"
    d = client.get("/api/dashboard").get_json()
    assert d["meetings"]["done"] == 1 and d["extraction_totals"]["action"] > 0
    h = client.get("/api/health").get_json()
    assert h["database"] and h["index"]["indexed_meetings"] == 1
    samples = client.get("/api/samples").get_json()["samples"]
    assert {s["name"] for s in samples} == {PLATFORM, REMOTE, STANDUP}
    assert client.post("/api/samples/run.py").status_code == 404  # only bundled .txt samples
