"""Unit tests for the ported notebook logic."""
import sys
from pathlib import Path

from app.services import summarization
from app.services.extraction import extract_information, get_owner
from app.services.text import Sentence, parse_turns


def test_parse_turns_both_formats():
    t = "[A] Hello there.\ncontinued line\nMaya: We will ship.\n"
    assert parse_turns(t) == [("A", "Hello there."), ("A", "continued line"), ("Maya", "We will ship.")]
    assert parse_turns("no tags here at all") == [(None, "no tags here at all")]


def test_owner_rules():
    assert get_owner("Daniel will update the webhooks.", "Maya") == "Daniel"
    assert get_owner("We will meet again.", "Maya") == "Maya"     # pronoun is not a name
    assert get_owner("I will write the report.", "C") == "C"
    assert get_owner("This is assigned to omar.", "Maya").lower() == "omar"
    assert get_owner("The sky is blue.", "Maya") is None


def test_extraction_kinds_and_no_invention():
    sents = [Sentence(0, "A", "We decided to use the blue case."),
             Sentence(1, "B", "There is a risk the chip is too expensive."),
             Sentence(2, "C", "I will send the drawings by Friday."),
             Sentence(3, "A", "Nice weather today, right?"),
             Sentence(4, "B", "The room is quiet.")]
    rows = extract_information(sents)
    kinds = {(r["kind"], r["sentence_index"]) for r in rows}
    assert ("decision", 0) in kinds and ("risk", 1) in kinds and ("action", 2) in kinds
    assert ("question", 3) in kinds and ("deadline", 2) in kinds
    assert not any(r["sentence_index"] == 4 for r in rows)    # nothing invented
    action = next(r for r in rows if r["kind"] == "action")
    assert action["owner"] == "C" and action["deadline"] == "by Friday"


def test_tfidf_summary_matches_notebook_rules():
    text = " ".join(f"Sentence number {i} talks about topic {i} in detail." for i in range(12))
    out = summarization.tfidf_summary(text)
    parts = [p for p in out.split(". ") if p]
    assert len(parts) == 6
    short = "Too short. Also short. This sentence is definitely longer than twenty chars."
    assert summarization.tfidf_summary(short) == "This sentence is definitely longer than twenty chars."


def test_hierarchical_chunking_logic(monkeypatch):
    """Checks the notebook's chunk -> summarise -> combine logic with a fake
    whitespace tokenizer and a fake one-chunk summariser (no model)."""

    class Tok:
        def tokenize(self, t):
            return t.split()

        def convert_tokens_to_ids(self, toks):
            return toks

        def decode(self, ids, **_):
            return " ".join(ids)

    calls = []

    def fake_one(tok, model, device, text):
        calls.append(len(text.split()))
        return " ".join(text.split()[:30])

    monkeypatch.setattr(summarization, "_summarize_one_chunk", fake_one)
    out = summarization.transformer_summary(Tok(), None, "cpu", "w " * 2000)
    # 2000 tokens -> 3 chunks of <=850, then one pass over the combined 90 tokens
    assert calls == [850, 850, 300, 90]
    assert len(out.split()) == 30


def test_abstractive_ok_path(monkeypatch):
    class Reg:
        class config:
            SUMMARIZER_MODEL = "sshleifer/distilbart-cnn-12-6"

        def summarizer(self):
            return "tok", "model", "cpu"

    monkeypatch.setattr(summarization, "transformer_summary", lambda *a: "An abstractive summary.")
    r = summarization.abstractive(Reg(), "text " * 50)
    assert r.status == "ok" and r.text == "An abstractive summary." and r.method == "distilbart"

    monkeypatch.setattr(summarization, "transformer_summary",
                        lambda *a: (_ for _ in ()).throw(MemoryError("oom")))
    r = summarization.abstractive(Reg(), "A sentence that is long enough to keep. " * 3)
    assert r.status == "fallback" and "MemoryError" in r.note


def test_ami_parser_on_minimal_fixture(tmp_path):
    """Hand-made two-speaker fixture in the AMI NITE XML layout."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import import_ami

    nite = 'xmlns:nite="http://nite.sourceforge.net/"'
    (tmp_path / "words").mkdir()
    (tmp_path / "segments").mkdir()
    (tmp_path / "abstractive").mkdir()
    for spk, words, start in (("A", ["Hello", "team", "."], "0.5"), ("B", ["Hi", "!"], "2.0")):
        w = "".join(f'<w nite:id="XX1000a.{spk}.words{i}">{t}</w>' for i, t in enumerate(words))
        (tmp_path / "words" / f"XX1000a.{spk}.words.xml").write_text(
            f'<nite:root {nite}>{w}</nite:root>', encoding="utf-8")
        last = len(words) - 1
        (tmp_path / "segments" / f"XX1000a.{spk}.segments.xml").write_text(
            f'<nite:root {nite}><segment nite:id="s{spk}" transcriber_start="{start}">'
            f'<nite:child href="XX1000a.{spk}.words.xml#id(XX1000a.{spk}.words0)..'
            f'id(XX1000a.{spk}.words{last})"/></segment></nite:root>', encoding="utf-8")
    (tmp_path / "abstractive" / "XX1000a.abssumm.xml").write_text(
        f'<nite:root {nite}><abstract><sentence>The team said hello.</sentence></abstract>'
        f'<actions><sentence>Not part of the summary.</sentence></actions></nite:root>',
        encoding="utf-8")

    rows = list(import_ami.load_from_annotations(tmp_path))
    assert rows == [("XX1000a", "[A] Hello team.\n[B] Hi!", "The team said hello.")]
