from pathlib import Path

import numpy as np

from app.rag.exceptions import RagError


class FaissStore:
    def _faiss(self):
        try:
            import faiss
        except Exception as exc:
            raise RagError(503, "EMBEDDING_MODEL_UNAVAILABLE", "FAISS kutubxonasi mavjud emas.") from exc
        return faiss

    def create(self, dimension: int):
        faiss = self._faiss()
        return faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))

    def _validate_vectors(self, vectors: np.ndarray) -> np.ndarray:
        array = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        if array.ndim != 2:
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vectorlar 2D bo'lishi kerak.")
        if not np.isfinite(array).all():
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vectorlar ichida yaroqsiz qiymatlar bor.")
        return array

    def add(self, index, vectors: np.ndarray, chunk_ids: np.ndarray) -> None:
        faiss = self._faiss()
        array = self._validate_vectors(vectors)
        ids = np.ascontiguousarray(np.asarray(chunk_ids, dtype=np.int64))
        if ids.ndim != 1 or len(ids) != array.shape[0]:
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector va chunk ID soni mos emas.")
        if len(np.unique(ids)) != len(ids):
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Takroriy chunk ID aniqlandi.")
        if array.shape[1] != index.d:
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector dimension indexga mos emas.")
        if len(ids) == 0:
            return
        faiss.normalize_L2(array)
        try:
            index.add_with_ids(array, ids)
        except Exception as exc:
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "FAISS indexga yozish muvaffaqiyatsiz tugadi.") from exc

    def search(self, index, query: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        if getattr(index, "ntotal", 0) == 0:
            return []
        array = self._validate_vectors(query)
        if array.shape != (1, index.d):
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Query vector o'lchami noto'g'ri.")
        self._faiss().normalize_L2(array)
        try:
            scores, ids = index.search(array, top_k)
        except Exception as exc:
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "FAISS qidiruvi muvaffaqiyatsiz tugadi.") from exc
        results: list[tuple[int, float]] = []
        for chunk_id, score in zip(ids[0].tolist(), scores[0].tolist()):
            if int(chunk_id) == -1:
                continue
            results.append((int(chunk_id), float(score)))
        return results

    def write(self, index, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._faiss().write_index(index, str(path))
        except Exception as exc:
            raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "FAISS artifactni yozib bo'lmadi.") from exc

    def read(self, path: Path):
        try:
            return self._faiss().read_index(str(path))
        except Exception as exc:
            raise RagError(500, "VECTOR_INDEX_CORRUPT", "FAISS artifact buzilgan yoki o'qilmadi.") from exc
