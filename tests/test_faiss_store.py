import numpy as np
import pytest

from app.rag.exceptions import RagError
from app.rag.faiss_store import FaissStore


def test_faiss_store_add_and_search_round_trip(tmp_path) -> None:
    store = FaissStore()
    index = store.create(4)
    vectors = np.asarray(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.8, 0.2, 0.0, 0.0],
        ],
        dtype=np.float32,
    )
    chunk_ids = np.asarray([10, 20], dtype=np.int64)
    store.add(index, vectors, chunk_ids)
    results = store.search(index, np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32), 2)
    assert results[0][0] == 10

    path = tmp_path / "index.faiss"
    store.write(index, path)
    restored = store.read(path)
    restored_results = store.search(restored, np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32), 2)
    assert restored_results[0][0] == 10


def test_faiss_store_rejects_duplicate_ids() -> None:
    store = FaissStore()
    index = store.create(4)
    with pytest.raises(RagError) as exc:
        store.add(
            index,
            np.asarray([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32),
            np.asarray([1, 1], dtype=np.int64),
        )
    assert exc.value.code == "VECTOR_INDEX_STORAGE_ERROR"
