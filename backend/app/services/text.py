"""Transcript cleaning and speaker-aware sentence splitting.

The notebook ran spaCy over the whole transcript as one string. That loses
speaker labels, and AMI transcripts use the "[B] text" format that the
notebook's owner regex ("Name: text") never matched. Here each speaker turn
is parsed first and spaCy splits turns into sentences, so every sentence
keeps its speaker. Both label styles are supported:

    [B] Okay, let's start.          (AMI export from the notebook)
    Maya: We need to migrate ...    (plain "Name:" transcripts)
"""
import re
from dataclasses import dataclass
from typing import List, Optional

AMI_TURN = re.compile(r"^\s*\[([A-Za-z0-9_ .'-]{1,40})\]\s*(.*)$")
NAMED_TURN = re.compile(r"^\s*([A-Z][A-Za-z .'-]{0,40}):\s*(.*)$")  # notebook's SPEAKER pattern


@dataclass
class Sentence:
    idx: int
    speaker: Optional[str]
    text: str


def clean_text(text: str) -> str:
    """Notebook's clean_text: drop NULs, collapse spaces/tabs, limit blank lines."""
    text = str(text).replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_turns(text: str):
    """Split a transcript into (speaker, utterance) turns, line by line.

    An untagged line continues the previous speaker's turn; a transcript
    with no tags at all becomes turns with speaker None.
    """
    turns = []
    current = None
    for raw in clean_text(text).split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = AMI_TURN.match(line) or NAMED_TURN.match(line)
        if m:
            current = m.group(1).strip()
            body = m.group(2).strip()
        else:
            body = line
        if body:
            turns.append((current, body))
    return turns


def split_sentences(nlp, text: str) -> List[Sentence]:
    turns = parse_turns(text)
    out: List[Sentence] = []
    bodies = (body for _, body in turns)
    for (speaker, _), doc in zip(turns, nlp.pipe(bodies, batch_size=64)):
        for sent in doc.sents:
            s = sent.text.strip()
            if s:
                out.append(Sentence(len(out), speaker, s))
    return out


def basic_stats(text: str, sentences: List[Sentence]) -> dict:
    speakers = {s.speaker for s in sentences if s.speaker}
    return {
        # Same word definition as the notebook's analytics (whitespace split).
        "word_count": len(str(text).split()),
        "sentence_count": len(sentences),
        "speaker_count": len(speakers),
    }
