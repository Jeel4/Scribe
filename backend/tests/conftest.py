"""Test fixtures.

The tests use the REAL spaCy model, TF-IDF, ROUGE and FAISS code. The
Hugging Face models (DistilBART, MiniLM, KeyBERT) are replaced as follows,
so the suite runs offline and fast:

* `FakeEmbedder` — a deterministic hashed bag-of-words vector. It is NOT a
  semantic model; it only exists to test that the FAISS index is built,
  searched, filtered by meeting and rebuilt after add/delete.
* the summariser and KeyBERT are reported as unavailable, which exercises
  the labelled fallback paths.
"""
import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from app import create_app
from app.models import ModelRegistry, ModelUnavailable

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


class FakeEmbedder:
    dim = 64

    def encode(self, texts, **_):
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]+", t.lower()):
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class FakeRegistry(ModelRegistry):
    def __init__(self, config, embedder=True):
        super().__init__(config)
        self._fake_embedder = FakeEmbedder() if embedder else None

    def embedder(self):
        if self._fake_embedder is None:
            raise ModelUnavailable("embedder disabled in this test")
        return self._fake_embedder

    def summarizer(self):
        raise ModelUnavailable("summariser disabled in tests (no Hugging Face access)")

    def keybert(self):
        raise ModelUnavailable("KeyBERT disabled in tests")


def _make_app(tmp_path, embedder=True):
    overrides = {"DATABASE_PATH": str(tmp_path / "test.db"), "ASYNC_ANALYSIS": False,
                 "TESTING": True}
    app = create_app(overrides, registry=None)
    cfg = app.extensions["scribe.config"]
    reg = FakeRegistry(cfg, embedder=embedder)
    app.extensions["scribe.registry"] = reg
    app.extensions["scribe.jobs"].registry = reg
    return app


@pytest.fixture
def app(tmp_path):
    return _make_app(tmp_path)


@pytest.fixture
def app_no_embedder(tmp_path):
    return _make_app(tmp_path, embedder=False)


@pytest.fixture
def client(app):
    return app.test_client()


def sample_text(name):
    return (SAMPLES / name).read_text(encoding="utf-8")


def upload(client, text, filename="meeting.txt", **form):
    import io

    data = {"file": (io.BytesIO(text.encode("utf-8") if isinstance(text, str) else text), filename)}
    data.update(form)
    return client.post("/api/meetings", data=data, content_type="multipart/form-data")
