"""Import AMI meetings (transcript + human reference summary) into Scribe.

This reuses the notebook's final AMI parser (segments + words XML, sorted
by segment start time, "[A] text" speaker turns; reference summary = the
<abstract> sentences of *.abssumm.xml). Imported meetings are analysed
with the same pipeline as uploads, so ROUGE is computed against the real
AMI references and appears on the Evaluation page.

You need the AMI manual annotations (ami_public_manual_1.6.2.zip) from the
AMI corpus website, extracted to a folder that contains words/, segments/
and abstractive/. Alternatively pass the CSV the notebook wrote
(ami_scribe_dataset.csv).

Examples (run from the backend folder):
    python scripts/import_ami.py --annotations ~/ami_annotations --limit 10
    python scripts/import_ami.py --csv ami_scribe_dataset.csv --only-with-summary
    python scripts/import_ami.py --annotations ~/ami --limit 5 --no-abstractive

DistilBART on CPU takes roughly 20-60 s per AMI meeting; use --limit first.
"""
import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

csv.field_size_limit(10**8)


# ---------------------------------------------------- notebook AMI parser
def tag_name(tag):
    return tag.split("}")[-1].lower()


def attrs_local(element):
    return {tag_name(k): v for k, v in element.attrib.items()}


def meeting_id(path):
    match = re.match(r"^([A-Za-z]+\d+[a-z])", path.name)
    return match.group(1) if match else None


def read_root(path):
    return ET.parse(path).getroot()


def get_words(path):
    words = {}
    for el in read_root(path).iter():
        if tag_name(el.tag) != "w":
            continue
        a = attrs_local(el)
        if a.get("id"):
            words[a["id"]] = " ".join("".join(el.itertext()).split())
    return words


def join_tokens(tokens):
    text = ""
    no_space_before = {".", ",", "?", "!", ";", ":", ")", "]", "}", "%"}
    no_space_after = {"(", "[", "{"}
    for token in tokens:
        if not token:
            continue
        if not text:
            text = token
        elif token in no_space_before or text[-1:] in no_space_after:
            text += token
        else:
            text += " " + token
    return text


def _float(v):
    try:
        return float(v) if v else None
    except ValueError:
        return None


def extract_segment_turns(segment_path, word_path):
    words = get_words(word_path)
    turns = []
    for seg in read_root(segment_path).iter():
        if tag_name(seg.tag) != "segment":
            continue
        a = attrs_local(seg)
        token_ids = []
        for child in seg.iter():
            if tag_name(child.tag) != "child":
                continue
            href = attrs_local(child).get("href", "")
            ids = re.findall(r"id\(([^)]+)\)", href)
            if len(ids) >= 2:
                first, last = ids[0], ids[1]
                m1, m2 = re.search(r"words(\d+)$", first), re.search(r"words(\d+)$", last)
                if m1 and m2:
                    stem = first.rsplit("words", 1)[0] + "words"
                    token_ids += [f"{stem}{i}" for i in range(int(m1.group(1)), int(m2.group(1)) + 1)
                                  if f"{stem}{i}" in words]
            elif len(ids) == 1:
                token_ids.append(ids[0])
        text = join_tokens([words[x] for x in token_ids if x in words])
        if text:
            turns.append({"start": _float(a.get("transcriber_start")), "text": text})
    return turns


def load_from_annotations(base: Path):
    words_dir, seg_dir, sum_dir = base / "words", base / "segments", base / "abstractive"
    for d in (words_dir, seg_dir):
        if not d.is_dir():
            sys.exit(f"Expected folder not found: {d}")
    word_paths = {p.name[: -len(".words.xml")]: p for p in words_dir.glob("*.words.xml")}
    seg_paths = {p.name[: -len(".segments.xml")]: p for p in seg_dir.glob("*.segments.xml")}

    speakers = {}
    for key, wp in word_paths.items():
        mid = meeting_id(wp)
        if mid and key in seg_paths:
            speakers.setdefault(mid, []).append(key)

    references = {}
    if sum_dir.is_dir():
        for path in sum_dir.glob("*.abssumm.xml"):
            mid = meeting_id(path)
            abstract = []
            for el in read_root(path).iter():
                if tag_name(el.tag) == "abstract":
                    for s in el.iter():
                        if tag_name(s.tag) == "sentence":
                            t = " ".join("".join(s.itertext()).split())
                            if t:
                                abstract.append(t)
            references[mid] = " ".join(abstract)

    for mid, keys in sorted(speakers.items()):
        turns = []
        for key in keys:
            m = re.search(r"\.([A-Z])$", key)
            spk = m.group(1) if m else "UNKNOWN"
            turns += [{**t, "speaker": spk} for t in extract_segment_turns(seg_paths[key], word_paths[key])]
        turns.sort(key=lambda t: (t["start"] is None, t["start"] or 0))
        transcript = "\n".join(f"[{t['speaker']}] {t['text']}" for t in turns)
        yield mid, transcript, references.get(mid, "")


def load_from_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            yield row["meeting_id"], row.get("transcript", ""), row.get("reference_summary", "") or ""


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--annotations", type=Path, help="extracted AMI manual annotations folder")
    src.add_argument("--csv", type=Path, help="ami_scribe_dataset.csv written by the notebook")
    ap.add_argument("--limit", type=int, default=None, help="import at most N meetings")
    ap.add_argument("--only-with-summary", action="store_true", help="skip meetings without a reference")
    ap.add_argument("--no-abstractive", action="store_true", help="skip DistilBART (much faster)")
    args = ap.parse_args()

    from app.config import Config
    from app.db import connect, init_db
    from app.models import ModelRegistry
    from app.services.analysis import run_analysis
    from app.services.retrieval import RetrievalIndex

    init_db(Config.DATABASE_PATH)
    registry, index = ModelRegistry(Config), RetrievalIndex(Config.DATABASE_PATH)
    options = {"abstractive": not args.no_abstractive}

    rows = load_from_annotations(args.annotations.expanduser()) if args.annotations \
        else load_from_csv(args.csv.expanduser())
    imported = 0
    for mid, transcript, reference in rows:
        if args.limit is not None and imported >= args.limit:
            break
        if not transcript.strip() or (args.only_with_summary and not reference.strip()):
            continue
        conn = connect(Config.DATABASE_PATH)
        try:
            if conn.execute("SELECT 1 FROM meetings WHERE source='ami' AND source_filename=?",
                            (mid,)).fetchone():
                print(f"skip {mid}: already imported")
                continue
            cur = conn.execute(
                "INSERT INTO meetings (title, source_filename, source, transcript, reference_summary, "
                "status, options_json, word_count) VALUES (?,?, 'ami', ?, ?, 'pending', ?, ?)",
                (f"AMI {mid}", mid, transcript, reference.strip() or None, json.dumps(options),
                 len(transcript.split())),
            )
            conn.commit()
            new_id = cur.lastrowid
        finally:
            conn.close()
        imported += 1
        print(f"analysing {mid} (meeting {new_id}) ...", flush=True)
        run_analysis(Config, registry, index, new_id, options)
        conn = connect(Config.DATABASE_PATH)
        r = conn.execute("SELECT status, error FROM meetings WHERE id=?", (new_id,)).fetchone()
        conn.close()
        print(f"  -> {r['status']}" + (f": {r['error']}" if r["error"] else ""))
    print(f"Imported {imported} meeting(s). Model status: {json.dumps(registry.status(), indent=1)}")


if __name__ == "__main__":
    main()
