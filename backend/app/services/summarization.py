"""Extractive (TF-IDF) and abstractive (DistilBART) summarisation.

Both functions are ported line-for-line from the notebook's AMI evaluation
cell — the code that produced the reported ROUGE scores:

* tfidf_summary: regex sentence split, sentences > 20 chars, score = sum of
  TF-IDF weights per sentence, keep the top 6 in original order.
* transformer_summary: tokenise, split into 850-token chunks, summarise each
  chunk (beam 4, no_repeat_ngram_size 3, 20–120 new tokens), then compress
  the concatenated chunk summaries hierarchically.

Why the notebook showed identical ROUGE for both methods: its later
`pipeline("summarization", ...)` call fails under transformers v5, which
set `summarizer = None`, and `summarize()` then silently returned the
TF-IDF summary. Here the abstractive path never hides a fallback — the
result carries status "fallback" and the reason.
"""
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from ..models import ModelUnavailable

CHUNK_TOKENS = 850


@dataclass
class SummaryResult:
    method: str          # "tfidf" | "distilbart"
    status: str          # "ok" | "fallback"
    text: str
    note: Optional[str] = None
    model_name: Optional[str] = None


# --------------------------------------------------------------- extractive
def tfidf_summary(text: str, max_sentences: int = 6) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", str(text).strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if not sentences:
        return str(text)[:1000]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    try:
        matrix = TfidfVectorizer(stop_words="english", max_features=5000).fit_transform(sentences)
        scores = np.asarray(matrix.sum(axis=1)).ravel()
    except ValueError:  # e.g. only stop words
        return " ".join(sentences[:max_sentences])
    chosen = sorted(np.argsort(scores)[-max_sentences:])
    return " ".join(sentences[i] for i in chosen)


def extractive(text: str) -> SummaryResult:
    return SummaryResult(
        "tfidf", "ok", tfidf_summary(text),
        note="Top 6 sentences by summed TF-IDF weight, in transcript order.",
        model_name="scikit-learn TfidfVectorizer",
    )


# --------------------------------------------------------------- abstractive
def _split_into_token_chunks(tokenizer, text, max_tokens=CHUNK_TOKENS):
    tokens = tokenizer.tokenize(str(text))
    chunks = []
    for start in range(0, len(tokens), max_tokens):
        ids = tokenizer.convert_tokens_to_ids(tokens[start:start + max_tokens])
        chunk = tokenizer.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _summarize_one_chunk(tokenizer, model, device, text):
    import torch

    with torch.inference_mode():
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=1024).to(device)
        output_ids = model.generate(
            **inputs,
            max_new_tokens=120,
            min_new_tokens=20,
            num_beams=4,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )
    return tokenizer.decode(
        output_ids[0], skip_special_tokens=True, clean_up_tokenization_spaces=False
    ).strip()


def transformer_summary(tokenizer, model, device, transcript: str) -> str:
    one = lambda t: _summarize_one_chunk(tokenizer, model, device, t)  # noqa: E731
    chunks = _split_into_token_chunks(tokenizer, transcript)
    if not chunks:
        return ""
    combined = " ".join(s for s in (one(c) for c in chunks) if s)
    if not combined:
        return ""
    if len(tokenizer.tokenize(combined)) <= CHUNK_TOKENS:
        return one(combined)
    second = _split_into_token_chunks(tokenizer, combined)
    combined_second = " ".join(s for s in (one(c) for c in second) if s)
    final_chunks = _split_into_token_chunks(tokenizer, combined_second)
    if len(final_chunks) <= 1:
        return one(final_chunks[0]) if final_chunks else combined_second
    return " ".join(one(c) for c in final_chunks[:3])


def abstractive(registry, text: str) -> SummaryResult:
    model_name = registry.config.SUMMARIZER_MODEL
    reason = None
    try:
        tokenizer, model, device = registry.summarizer()
        summary = transformer_summary(tokenizer, model, device, text)
        if summary.strip():
            return SummaryResult("distilbart", "ok", summary,
                                 note=f"Chunked abstractive summary on {device}.",
                                 model_name=model_name)
        reason = "The model returned an empty summary."
    except ModelUnavailable as exc:
        reason = f"DistilBART could not be loaded ({exc})."
    except Exception as exc:  # noqa: BLE001 - e.g. out of memory during generate
        reason = f"DistilBART failed while generating ({type(exc).__name__}: {str(exc)[:200]})."

    return SummaryResult(
        "distilbart", "fallback", tfidf_summary(text),
        note=reason + " The text shown is the TF-IDF extractive summary, NOT a DistilBART output.",
        model_name=model_name,
    )
