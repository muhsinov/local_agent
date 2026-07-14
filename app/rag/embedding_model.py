import gc
import threading
from abc import ABC, abstractmethod

import numpy as np

from app.config import Settings
from app.rag.exceptions import RagError


class EmbeddingModel(ABC):
    @abstractmethod
    def encode_documents(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def encode_query(self, text: str) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def get_dimension(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class SentenceTransformerEmbeddingModel(EmbeddingModel):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._model = None
        self._module = None

    def _load_model_locked(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RagError(
                503,
                "EMBEDDING_MODEL_UNAVAILABLE",
                "Embedding model kutubxonasi mavjud emas yoki yuklanmadi.",
            ) from exc
        try:
            model = SentenceTransformer(
                self._settings.embedding_model_name,
                device=self._settings.embedding_device,
                trust_remote_code=False,
                local_files_only=self._settings.embedding_local_files_only,
            )
        except Exception as exc:
            raise RagError(
                503,
                "EMBEDDING_MODEL_UNAVAILABLE",
                "Embedding modelni yuklab bo'lmadi. prepare_embeddings.ps1 orqali tayyorlang.",
            ) from exc
        model.max_seq_length = self._settings.embedding_max_sequence_length
        if hasattr(model, "eval"):
            model.eval()
        dimension = int(model.get_sentence_embedding_dimension())
        if dimension != self._settings.embedding_dimension:
            raise RagError(
                500,
                "EMBEDDING_MODEL_DIMENSION_MISMATCH",
                "Embedding model dimension qiymati kutilgan konfiguratsiyaga mos emas.",
            )
        self._module = SentenceTransformer
        self._model = model
        return model

    def _with_model(self):
        with self._lock:
            return self._load_model_locked()

    def _validate_output(self, output: np.ndarray, expected_rows: int) -> np.ndarray:
        array = np.asarray(output, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2 or array.shape[0] != expected_rows or array.shape[1] != self._settings.embedding_dimension:
            raise RagError(500, "EMBEDDING_INVALID_RESPONSE", "Embedding model noto'g'ri o'lchamdagi javob qaytardi.")
        if not np.isfinite(array).all():
            raise RagError(500, "EMBEDDING_INVALID_RESPONSE", "Embedding javobida yaroqsiz qiymatlar bor.")
        norms = np.linalg.norm(array, axis=1)
        if np.any(norms <= 0):
            raise RagError(500, "EMBEDDING_INVALID_RESPONSE", "Embedding javobida bo'sh vektor aniqlandi.")
        return array

    def _encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._settings.embedding_dimension), dtype=np.float32)
        model = self._with_model()
        try:
            vectors = model.encode(
                texts,
                batch_size=self._settings.embedding_batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return self._validate_output(vectors, len(texts))
        except RagError:
            raise
        except Exception as exc:
            raise RagError(500, "EMBEDDING_INVALID_RESPONSE", "Embedding hisoblashda xatolik yuz berdi.") from exc
        finally:
            if not self._settings.embedding_keep_loaded:
                self.close()

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([text])

    def get_dimension(self) -> int:
        model = self._with_model()
        dimension = int(model.get_sentence_embedding_dimension())
        if not self._settings.embedding_keep_loaded:
            self.close()
        return dimension

    def close(self) -> None:
        with self._lock:
            self._model = None
            gc.collect()
