"""Meeting upload, listing, detail, re-analysis, reference summary, delete."""
import json
import re
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

from ..config import BACKEND_DIR
from ..services.analysis import rescore_meeting
from ..services.extraction import KINDS
from .common import bad_request, cfg, db, index, jobs, loads, parse_bool

bp = Blueprint("meetings", __name__)

SAMPLES_DIR = Path(BACKEND_DIR).parent / "samples"
MAX_TITLE = 200
MAX_REFERENCE_CHARS = 50_000


# ------------------------------------------------------------- validation
def decode_text_file(storage, label):
    """Read an uploaded file as UTF-8 text. The bytes stay in memory: they
    are never saved under the user's filename and never executed."""
    name = (storage.filename or "").strip()
    if not name.lower().endswith(".txt"):
        bad_request(f"{label} must be a .txt file.")
    raw = storage.read()
    limit = int(cfg().MAX_UPLOAD_MB * 1024 * 1024)
    if len(raw) > limit:
        abort(413)
    if not raw.strip():
        bad_request(f"{label} is empty.")
    if b"\x00" in raw[:4096]:
        bad_request(f"{label} looks like a binary file, not plain text.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        bad_request(f"{label} is not valid UTF-8 text. Re-save it as UTF-8 and try again.")
    return name, text


def validate_transcript(text):
    words = len(text.split())
    if words < cfg().MIN_TRANSCRIPT_WORDS:
        bad_request(
            f"The transcript has only {words} words; at least "
            f"{cfg().MIN_TRANSCRIPT_WORDS} are needed for a meaningful analysis."
        )
    return text


def clean_title(title, fallback):
    title = re.sub(r"\s+", " ", (title or "").strip())[:MAX_TITLE]
    return title or fallback


def create_meeting(title, transcript, filename, source, reference, abstractive):
    options = {"abstractive": abstractive}
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO meetings (title, source_filename, source, transcript, reference_summary, "
            "status, options_json, word_count) VALUES (?,?,?,?,?, 'pending', ?, ?)",
            (title, filename, source, transcript, reference or None, json.dumps(options),
             len(transcript.split())),
        )
        conn.commit()
        meeting_id = cur.lastrowid
    finally:
        conn.close()
    jobs().submit(meeting_id, options)
    return meeting_id


# ------------------------------------------------------------ serialising
def meeting_row(r):
    return {
        "id": r["id"], "title": r["title"], "source": r["source"],
        "source_filename": r["source_filename"], "status": r["status"], "stage": r["stage"],
        "error": r["error"], "word_count": r["word_count"], "sentence_count": r["sentence_count"],
        "speaker_count": r["speaker_count"], "has_reference": bool(r["reference_summary"]),
        "created_at": r["created_at"], "analyzed_at": r["analyzed_at"],
        "options": loads(r["options_json"], {}), "notes": loads(r["notes_json"], []),
    }


def get_meeting_or_404(conn, meeting_id):
    r = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    if r is None:
        abort(404, description=f"Meeting {meeting_id} does not exist (it may have been deleted).")
    return r


def meeting_detail(conn, r):
    mid = r["id"]
    out = meeting_row(r)
    out["reference_summary"] = r["reference_summary"]
    out["summaries"] = {
        s["method"]: {
            "status": s["status"], "text": s["text"], "note": s["note"], "model_name": s["model_name"],
            "rouge": None if s["rouge1"] is None else
            {"rouge1": s["rouge1"], "rouge2": s["rouge2"], "rougeL": s["rougeL"]},
        }
        for s in conn.execute("SELECT * FROM summaries WHERE meeting_id=?", (mid,))
    }
    out["entities"] = [dict(e) for e in conn.execute(
        "SELECT text, label, count FROM entities WHERE meeting_id=? ORDER BY count DESC, text", (mid,))]
    kws = conn.execute("SELECT keyword, score, method FROM keywords WHERE meeting_id=? ORDER BY rank",
                       (mid,)).fetchall()
    out["keywords"] = [{"keyword": k["keyword"], "score": k["score"]} for k in kws]
    out["keyword_method"] = kws[0]["method"] if kws else None
    items = {k: [] for k in KINDS}
    for e in conn.execute("SELECT kind, text, owner, deadline, speaker, sentence_index FROM extractions "
                          "WHERE meeting_id=? ORDER BY sentence_index", (mid,)):
        items.setdefault(e["kind"], []).append({
            "text": e["text"], "owner": e["owner"], "deadline": e["deadline"],
            "speaker": e["speaker"], "sentence_index": e["sentence_index"],
        })
    out["extractions"] = items
    out["sentences"] = [
        {"idx": s["idx"], "speaker": s["speaker"], "text": s["text"]}
        for s in conn.execute("SELECT idx, speaker, text FROM sentences WHERE meeting_id=? ORDER BY idx",
                              (mid,))
    ]
    out["embedded"] = conn.execute(
        "SELECT COUNT(*) FROM sentences WHERE meeting_id=? AND embedding IS NOT NULL", (mid,)
    ).fetchone()[0] > 0
    return out


# ----------------------------------------------------------------- routes
@bp.get("/meetings")
def list_meetings():
    conn = db()
    try:
        rows = conn.execute("SELECT * FROM meetings ORDER BY created_at DESC, id DESC").fetchall()
        counts = {}
        for c in conn.execute("SELECT meeting_id, kind, COUNT(*) n FROM extractions GROUP BY meeting_id, kind"):
            counts.setdefault(c["meeting_id"], {})[c["kind"]] = c["n"]
        out = []
        for r in rows:
            m = meeting_row(r)
            m["extraction_counts"] = {k: counts.get(r["id"], {}).get(k, 0) for k in KINDS}
            out.append(m)
        return jsonify(meetings=out)
    finally:
        conn.close()


@bp.post("/meetings")
def upload_meeting():
    """multipart/form-data: file (.txt, required), title, reference_file
    (.txt) or reference_summary (text), abstractive (true/false)."""
    if "file" not in request.files or not request.files["file"].filename:
        bad_request("Choose a .txt transcript to upload.")
    filename, transcript = decode_text_file(request.files["file"], "The transcript")
    validate_transcript(transcript)

    reference = (request.form.get("reference_summary") or "").strip()
    ref_file = request.files.get("reference_file")
    if ref_file and ref_file.filename:
        _, reference = decode_text_file(ref_file, "The reference summary")
        reference = reference.strip()
    if len(reference) > MAX_REFERENCE_CHARS:
        bad_request("The reference summary is too long (max 50,000 characters).")

    title = clean_title(request.form.get("title"), Path(filename).stem.replace("_", " "))
    abstractive = parse_bool(request.form.get("abstractive"), True)
    mid = create_meeting(title, transcript, Path(filename).name[:MAX_TITLE], "upload", reference, abstractive)
    return jsonify(id=mid, status="pending"), 202


@bp.get("/meetings/<int:meeting_id>")
def get_meeting(meeting_id):
    conn = db()
    try:
        return jsonify(meeting_detail(conn, get_meeting_or_404(conn, meeting_id)))
    finally:
        conn.close()


@bp.get("/meetings/<int:meeting_id>/status")
def meeting_status(meeting_id):
    """Cheap endpoint the frontend polls while analysis runs."""
    conn = db()
    try:
        r = get_meeting_or_404(conn, meeting_id)
        return jsonify(id=r["id"], status=r["status"], stage=r["stage"], error=r["error"])
    finally:
        conn.close()


@bp.post("/meetings/<int:meeting_id>/analyze")
def reanalyze(meeting_id):
    body = request.get_json(silent=True) or {}
    conn = db()
    try:
        r = get_meeting_or_404(conn, meeting_id)
        if r["status"] in ("pending", "running"):
            abort(409, description="This meeting is already being analysed.")
        options = loads(r["options_json"], {})
        options["abstractive"] = parse_bool(body.get("abstractive"), options.get("abstractive", True))
        conn.execute("UPDATE meetings SET status='pending', stage=NULL, error=NULL, options_json=? WHERE id=?",
                     (json.dumps(options), meeting_id))
        conn.commit()
    finally:
        conn.close()
    index().mark_dirty()  # its old sentences leave search until the new run finishes
    jobs().submit(meeting_id, options)
    return jsonify(id=meeting_id, status="pending"), 202


@bp.put("/meetings/<int:meeting_id>/reference")
def set_reference(meeting_id):
    """Store (or clear, with an empty string) a human reference summary and
    recompute ROUGE for the existing summaries — models are not re-run."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("reference_summary", None), str):
        bad_request("Send JSON: {\"reference_summary\": \"...\"} (an empty string clears it).")
    reference = body["reference_summary"].strip()
    if len(reference) > MAX_REFERENCE_CHARS:
        bad_request("The reference summary is too long (max 50,000 characters).")
    conn = db()
    try:
        get_meeting_or_404(conn, meeting_id)
        conn.execute("UPDATE meetings SET reference_summary=? WHERE id=?", (reference or None, meeting_id))
        rescore_meeting(conn, meeting_id, reference)
        conn.commit()
        return jsonify(meeting_detail(conn, get_meeting_or_404(conn, meeting_id)))
    finally:
        conn.close()


@bp.delete("/meetings/<int:meeting_id>")
def delete_meeting(meeting_id):
    conn = db()
    try:
        get_meeting_or_404(conn, meeting_id)
        conn.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))  # cascades
        conn.commit()
    finally:
        conn.close()
    index().mark_dirty()
    return jsonify(deleted=meeting_id)


# ---------------------------------------------------------------- samples
def list_sample_files():
    if not SAMPLES_DIR.is_dir():
        return []
    return sorted(p for p in SAMPLES_DIR.glob("*.txt") if not p.name.endswith(".reference.txt"))


@bp.get("/samples")
def samples():
    out = []
    for p in list_sample_files():
        ref = p.with_name(p.stem + ".reference.txt")
        out.append({"name": p.name, "words": len(p.read_text(encoding="utf-8").split()),
                    "has_reference": ref.exists()})
    return jsonify(samples=out)


@bp.post("/samples/<name>")
def load_sample(name):
    """Import one of the bundled, clearly labelled synthetic transcripts."""
    match = next((p for p in list_sample_files() if p.name == name), None)
    if match is None:
        abort(404, description="Unknown sample.")
    transcript = match.read_text(encoding="utf-8")
    ref_path = match.with_name(match.stem + ".reference.txt")
    reference = ref_path.read_text(encoding="utf-8").strip() if ref_path.exists() else ""
    body = request.get_json(silent=True) or {}
    title = "[Synthetic sample] " + match.stem.replace("synthetic_", "").replace("_", " ").title()
    mid = create_meeting(title, transcript, match.name, "sample", reference,
                         parse_bool(body.get("abstractive"), True))
    return jsonify(id=mid, status="pending"), 202
