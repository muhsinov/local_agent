from app.rag.index_builder import build_embeddings
from app.rag.index_manager import rebuild_vector_index
from app.services.document_service import create_document
from app.database import initialize_database
from tests.conftest import FakeEmbeddingModel, build_settings


def _seed_documents(settings, count: int) -> None:
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        name = f"doc-{index}.txt"
        text = f"sample text {index} " * 30
        (settings.resolved_upload_directory / name).write_text(text, encoding="utf-8")
        (settings.resolved_extracted_text_directory / f"{name}.txt").write_text(text, encoding="utf-8")
        create_document(
            settings,
            file_name=name,
            file_path=name,
            file_type="txt",
            size_bytes=len(text.encode("utf-8")),
            sha256=f"sha-{index}",
            status="ready",
            text_path=f"{name}.txt",
            char_count=len(text),
            page_count=None,
            warning_code=None,
        )


def test_build_embeddings_uses_batches() -> None:
    model = FakeEmbeddingModel(dimension=64)
    chunks = [
        type("Chunk", (), {"text": f"text {index}"})()
        for index in range(9)
    ]
    vectors = build_embeddings(model, chunks, batch_size=4)
    assert vectors.shape == (9, 64)
    assert model.batch_sizes == [4, 4, 1]


def test_rebuild_keeps_model_loaded_for_single_operation(tmp_path) -> None:
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=64, EMBEDDING_BATCH_SIZE=3)
    initialize_database(settings)
    _seed_documents(settings, 2)
    model = FakeEmbeddingModel(dimension=64)
    rebuild_vector_index(settings, embedding_model=model)
    assert model.load_count == 1
    assert model.unload_count == 1
    assert model.max_batch_seen <= 3
