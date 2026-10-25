"""Lazy, thread-safe loading of the pretrained NLP models.

Each model is loaded at most once per process and then reused. If loading
fails (no internet on first run, missing package, out of memory) the error
is remembered and reported through /api/health, and the services that
depend on that model fall back transparently instead of crashing.
"""
import logging
import threading

log = logging.getLogger(__name__)


class ModelUnavailable(RuntimeError):
    """Raised when a model could not be loaded."""


class ModelRegistry:
    def __init__(self, config):
        self.config = config
        # Re-entrant: the KeyBERT loader itself asks for the embedder.
        self._lock = threading.RLock()
        self._models = {}
        self._errors = {}
        self._device = None

    # ------------------------------------------------------------------ utils
    def device(self) -> str:
        if self._device is None:
            wanted = self.config.DEVICE
            if wanted == "auto":
                try:
                    import torch

                    wanted = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:  # torch missing entirely
                    wanted = "cpu"
            self._device = wanted
        return self._device

    def _get(self, name, loader):
        with self._lock:
            if name in self._models:
                return self._models[name]
            if name in self._errors:
                raise ModelUnavailable(self._errors[name])
            try:
                log.info("Loading model: %s", name)
                obj = loader()
            except Exception as exc:  # noqa: BLE001 - we want every failure
                msg = f"{type(exc).__name__}: {exc}"
                log.warning("Could not load %s: %s", name, msg)
                self._errors[name] = msg[:500]
                raise ModelUnavailable(self._errors[name]) from exc
            self._models[name] = obj
            return obj

    def status(self) -> dict:
        names = {
            "spacy": self.config.SPACY_MODEL,
            "summarizer": self.config.SUMMARIZER_MODEL,
            "embedder": self.config.EMBEDDING_MODEL,
            "keybert": "KeyBERT (uses the embedder)",
        }
        out = {}
        for key, model_name in names.items():
            if key in self._models:
                state = "loaded"
            elif key in self._errors:
                state = "unavailable"
            else:
                state = "not_loaded"
            out[key] = {"model": model_name, "state": state, "error": self._errors.get(key)}
        out["device"] = self._device or "not_resolved"
        return out

    def retry_failed(self):
        """Forget previous load errors so the next request tries again."""
        with self._lock:
            self._errors.clear()

    # ----------------------------------------------------------------- models
    def spacy(self):
        def load():
            import spacy

            nlp = spacy.load(self.config.SPACY_MODEL)
            # AMI meetings reach ~50k characters; keep a generous ceiling.
            nlp.max_length = max(nlp.max_length, 2_000_000)
            return nlp

        return self._get("spacy", load)

    def summarizer(self):
        """(tokenizer, model, device) for DistilBART, as in the notebook's
        evaluation cell. The `pipeline("summarization")` call used later in
        the notebook no longer exists in transformers v5, so it is not used."""

        def load():
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            from transformers.utils import logging as hf_logging

            hf_logging.set_verbosity_error()  # silence per-call generation warnings
            dev = self.device()
            tok = AutoTokenizer.from_pretrained(self.config.SUMMARIZER_MODEL)
            mdl = AutoModelForSeq2SeqLM.from_pretrained(self.config.SUMMARIZER_MODEL).to(dev)
            mdl.eval()
            # Same generation-config adjustment as the notebook; the
            # explicit max_new_tokens / min_new_tokens take precedence.
            mdl.generation_config.max_length = 20
            mdl.generation_config.min_length = 0
            return tok, mdl, dev

        return self._get("summarizer", load)

    def embedder(self):
        def load():
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(self.config.EMBEDDING_MODEL, device=self.device())

        return self._get("embedder", load)

    def keybert(self):
        def load():
            from keybert import KeyBERT

            return KeyBERT(model=self.embedder())

        return self._get("keybert", load)

    def preload(self):
        for loader in (self.spacy, self.embedder, self.keybert, self.summarizer):
            try:
                loader()
            except ModelUnavailable:
                pass
