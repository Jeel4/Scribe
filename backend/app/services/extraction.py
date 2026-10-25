"""Rule-based extraction of candidate action items, decisions, risks,
open questions and deadlines.

The regular expressions are copied unchanged from the notebook. They are an
interpretable baseline, NOT a validated extractor: they produce candidates
with false positives (e.g. the action pattern contains `will .*`, which
matches almost any sentence containing "will") and false negatives.

Two documented corrections to owner attribution:
1. The speaker now comes from the parsed turn ("[B]" or "Name:"), so
   "I will ..." resolves to the speaker in AMI transcripts as well.
2. Sentence-initial pronouns/determiners ("We will", "It should") are no
   longer reported as a person's name.
"""
import re
from typing import List

from .text import Sentence

ACTION = re.compile(r"\b(i will|we will|will .*|need to|needs to|should|must|please|assigned to|responsible for|action item)\b", re.I)
DECISION = re.compile(r"\b(we decided|decision is|agreed to|approved|will proceed|we will use|we agreed|postponed|deferred)\b", re.I)
RISK = re.compile(r"\b(risk|may not|might not|could fail|unresolved|blocked|issue|bug|delay|concern|problem)\b", re.I)
QUESTION = re.compile(r"\?|\b(open question|remains open|need confirmation|not yet decided)\b", re.I)
DEADLINE = re.compile(r"\b(today|tomorrow|tonight|this week|next week|by (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|before the next release|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.I)

NAMED_OWNER = re.compile(r"\b([A-Z][a-z]+)\s+(?:will|should|must|can)\b")
ASSIGNED = re.compile(r"\bassigned to\s+([A-Z][a-z]+)\b", re.I)
NOT_A_NAME = {
    "I", "We", "You", "It", "That", "This", "These", "Those", "They", "He", "She",
    "There", "What", "Which", "Who", "Someone", "Somebody", "Everyone", "Everybody",
    "Anyone", "Anybody", "Nobody", "One", "Each", "All", "Both", "Then", "So", "And",
    "But", "Or", "If", "Maybe", "Yeah", "Yes", "No", "Okay", "Well", "Um", "Uh",
}

KINDS = ("action", "decision", "risk", "question", "deadline")


def get_owner(sentence: str, speaker):
    for m in NAMED_OWNER.finditer(sentence):
        if m.group(1) not in NOT_A_NAME:
            return m.group(1)
    if re.search(r"\bI will\b", sentence, re.I):
        return speaker
    assigned = ASSIGNED.search(sentence)
    if assigned:
        return assigned.group(1)
    return speaker if ACTION.search(sentence) else None


def extract_information(sentences: List[Sentence]) -> List[dict]:
    """Return flat rows: {kind, text, owner, deadline, speaker, sentence_index}."""
    rows = []
    seen = {k: set() for k in KINDS}

    def add(kind, s, owner=None, deadline=None, dedupe_key=None):
        key = dedupe_key or s.text
        if key in seen[kind]:
            return
        seen[kind].add(key)
        rows.append({"kind": kind, "text": s.text, "owner": owner, "deadline": deadline,
                     "speaker": s.speaker, "sentence_index": s.idx})

    for s in sentences:
        owner = get_owner(s.text, s.speaker)
        deadlines = DEADLINE.findall(s.text)
        if ACTION.search(s.text):
            # Action items are not de-duplicated in the notebook; keep that,
            # but a sentence can only be one action item.
            add("action", s, owner, ", ".join(deadlines) or None, dedupe_key=f"{s.idx}")
        if DECISION.search(s.text):
            add("decision", s)
        if RISK.search(s.text):
            add("risk", s)
        if QUESTION.search(s.text):
            add("question", s)
        for d in deadlines:
            add("deadline", s, owner, d, dedupe_key=f"{s.idx}:{d.lower()}")
    return rows
