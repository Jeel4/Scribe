"""Named entities (spaCy) and keywords (KeyBERT), as in the notebook."""
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from ..models import ModelUnavailable
from .text import clean_text, parse_turns


def extract_entities(nlp, text: str):
    """spaCy NER over the spoken text (speaker tags removed so "[B]" is never
    tagged as an entity). Repeated mentions are grouped with a count."""
    spoken = "\n".join(body for _, body in parse_turns(text))
    counts = Counter()
    for ent in nlp(spoken).ents:
        value = " ".join(ent.text.split())
        if value:
            counts[(value, ent.label_)] += 1
    return [{"text": t, "label": l, "count": c} for (t, l), c in counts.most_common()]


def extract_keywords(registry, text: str, top_n: int = 8):
    """KeyBERT with the notebook's settings: 1-3-grams, English stop words,
    MMR with diversity 0.45, top 8.

    Known limitation (kept from the notebook): KeyBERT embeds the whole
    document with MiniLM, which truncates input to ~256 word pieces, so the
    document vector mostly reflects the opening of a long meeting.

    Returns (keywords, method). If KeyBERT cannot be loaded, the notebook's
    TF-IDF fallback is used and labelled as such.

    Change from the notebook: speaker labels are removed first. With
    "Maya: ..." transcripts the speakers' names otherwise dominate the
    keyword list (AMI's one-letter "[B]" tags were dropped by the tokeniser
    anyway, so AMI results are unaffected).
    """
    cleaned = clean_text("\n".join(body for _, body in parse_turns(text)))
    try:
        kw_model = registry.keybert()
        pairs = kw_model.extract_keywords(
            cleaned, keyphrase_ngram_range=(1, 3), stop_words="english",
            top_n=top_n, use_mmr=True, diversity=0.45,
        )
        return [{"keyword": k, "score": float(v)} for k, v in pairs], "keybert"
    except ModelUnavailable:
        pass

    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=top_n)
    try:
        mat = vec.fit_transform([cleaned])
    except ValueError:
        return [], "tfidf_fallback"
    terms = vec.get_feature_names_out()
    vals = mat.toarray()[0]
    order = np.argsort(vals)[::-1][:top_n]
    return [{"keyword": str(terms[i]), "score": float(vals[i])} for i in order], "tfidf_fallback"
