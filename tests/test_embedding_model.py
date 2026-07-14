import sys
import types

import numpy as np
import pytest

from app.rag.embedding_model import SentenceTransformerEmbeddingModel
from app.rag.exceptions import RagError
from tests.conftest import build_settings


class StubSentenceTransformer:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.max_seq_length = None

    def eval(self) -> None:
        return None

    def get_sentence_embedding_dimension(self) -> int:
        return 64

    def encode(self, texts, **kwargs):
        return np.asarray([[1.0] + [0.0] * 63 for _ in texts], dtype=np.float32)


def test_embedding_model_lazy_loads_and_encodes(monkeypatch, tmp_path) -> None:
    stub_module = types.SimpleNamespace(SentenceTransformer=StubSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub_module)
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=64)
    model = SentenceTransformerEmbeddingModel(settings)
    vectors = model.encode_documents(["salom", "dunyo"])
    assert vectors.shape == (2, 64)
    assert vectors.dtype == np.float32


def test_embedding_model_dimension_mismatch_raises(monkeypatch, tmp_path) -> None:
    stub_module = types.SimpleNamespace(SentenceTransformer=StubSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub_module)
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=128)
    model = SentenceTransformerEmbeddingModel(settings)
    with pytest.raises(RagError) as exc:
        model.get_dimension()
    assert exc.value.code == "EMBEDDING_MODEL_DIMENSION_MISMATCH"
