import json
import os
import shutil
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np

from app.config import Settings
from app.database import connection_scope
from app.rag.embedding_model import EmbeddingModel, SentenceTransformerEmbeddingModel
from app.rag.exceptions import RagError
from app.rag.faiss_store import FaissStore
from app.rag.index_builder import build_chunks_for_documents, build_embeddings, collect_indexable_documents
from app.rag.models import VectorIndexManifest, VectorIndexStateSnapshot
from app.services.chunk_service import clear_chunks, replace_all_chunks


def _vector_root(settings: Settings) -> Path:
    return settings.resolved_vector_store_directory


def _generation_root(settings: Settings) -> Path:
    return _vector_root(settings) / "generations"


def ensure_vector_directories(settings: Settings) -> None:
    _generation_root(settings).mkdir(parents=True, exist_ok=True)


def _generation_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex}"


def _generation_dir(settings: Settings, generation_id: str) -> Path:
    return _generation_root(settings) / generation_id


def _building_dir(settings: Settings, generation_id: str) -> Path:
    return _generation_root(settings) / f"{generation_id}.building"


def _manifest_path(directory: Path) -> Path:
    return directory / "manifest.json"


def _index_path(directory: Path) -> Path:
    return directory / "index.faiss"


def _read_manifest(path: Path) -> VectorIndexManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return VectorIndexManifest(**data)
    except OSError as exc:
        raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector index manifestini o'qib bo'lmadi.") from exc
    except Exception as exc:
        raise RagError(409, "VECTOR_INDEX_CORRUPT", "Vector index manifestini o'qib bo'lmadi.") from exc


def _write_manifest(path: Path, manifest: VectorIndexManifest) -> None:
    payload = json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True)
    part_path = path.with_suffix(".json.part")
    try:
        with open(part_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part_path, path)
    except OSError as exc:
        try:
            part_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector index manifestini yozib bo'lmadi.") from exc


def _load_state(connection: sqlite3.Connection) -> VectorIndexStateSnapshot:
    row = connection.execute(
        """
        SELECT status, active_generation, dirty, document_count, chunk_count, embedding_model, embedding_dimension
        FROM vector_index_state
        WHERE id = 1;
        """
    ).fetchone()
    return VectorIndexStateSnapshot(
        status=str(row["status"]),
        active_generation=str(row["active_generation"]) if row["active_generation"] is not None else None,
        dirty=bool(row["dirty"]),
        document_count=int(row["document_count"]),
        chunk_count=int(row["chunk_count"]),
        embedding_model=str(row["embedding_model"]) if row["embedding_model"] is not None else None,
        embedding_dimension=int(row["embedding_dimension"]) if row["embedding_dimension"] is not None else None,
    )


def get_vector_index_status(settings: Settings) -> VectorIndexStateSnapshot:
    with connection_scope(settings) as connection:
        return _load_state(connection)


def _fsync_file(path: Path) -> None:
    try:
        with open(path, "r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector index faylini diskka yozib bo'lmadi.") from exc


def _cleanup_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _cleanup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _prune_generations(settings: Settings, keep_generation: str | None) -> None:
    root = _generation_root(settings)
    if not root.exists():
        return
    generation_dirs = sorted([path for path in root.iterdir() if path.is_dir() and not path.name.endswith(".building")])
    keep: set[str] = set()
    if keep_generation:
        keep.add(keep_generation)
    for path in reversed(generation_dirs):
        if path.name in keep:
            continue
        if len(keep) < settings.vector_index_generation_retention:
            keep.add(path.name)
            continue
        _cleanup_directory(path)


def _validate_ready_index(
    settings: Settings,
    state: VectorIndexStateSnapshot,
    *,
    db_chunk_count: int,
):
    if state.status != "ready" or state.dirty or not state.active_generation:
        raise RagError(409, "VECTOR_INDEX_CORRUPT", "Vector index tayyor holatda emas.")
    generation_dir = _generation_dir(settings, state.active_generation)
    if not generation_dir.exists():
        raise RagError(409, "VECTOR_INDEX_CORRUPT", "Faol vector index artifact topilmadi.")
    manifest = _read_manifest(_manifest_path(generation_dir))
    index = FaissStore().read(_index_path(generation_dir))
    if (
        manifest.generation_id != state.active_generation
        or manifest.embedding_model != state.embedding_model
        or manifest.embedding_dimension != state.embedding_dimension
        or manifest.chunk_count != state.chunk_count
        or manifest.document_count != state.document_count
        or manifest.chunk_count != db_chunk_count
        or int(index.ntotal) != state.chunk_count
        or index.d != state.embedding_dimension
        or manifest.metric != "cosine"
        or manifest.faiss_index_type != "IndexIDMap2(IndexFlatIP)"
    ):
        raise RagError(409, "VECTOR_INDEX_CORRUPT", "Vector index holati va artifactlari bir-biriga mos emas.")
    return manifest, index


def reconcile_vector_index(settings: Settings) -> None:
    ensure_vector_directories(settings)
    root = _generation_root(settings)
    for path in root.glob("*.building"):
        _cleanup_directory(path)
    with connection_scope(settings) as connection:
        connection.execute("BEGIN;")
        try:
            state = _load_state(connection)
            if state.status == "ready":
                try:
                    db_chunk_count = int(connection.execute("SELECT COUNT(*) FROM document_chunks;").fetchone()[0])
                    _validate_ready_index(settings, state, db_chunk_count=db_chunk_count)
                except RagError:
                    connection.execute(
                        """
                        UPDATE vector_index_state
                        SET status = 'error',
                            dirty = 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1;
                        """
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    with connection_scope(settings) as connection:
        state = _load_state(connection)
    _prune_generations(settings, state.active_generation)


def rebuild_vector_index(
    settings: Settings,
    *,
    requested_document_id: int | None = None,
    embedding_model: EmbeddingModel | None = None,
) -> VectorIndexStateSnapshot:
    ensure_vector_directories(settings)
    owned_model = embedding_model is None
    active_model = embedding_model or SentenceTransformerEmbeddingModel(settings)
    generation_id = _generation_id()
    build_dir = _building_dir(settings, generation_id)
    final_dir = _generation_dir(settings, generation_id)
    index_part = build_dir / "index.faiss.part"
    manifest_part = build_dir / "manifest.json.part"
    generation_committed = False

    with connection_scope(settings) as connection:
        documents = collect_indexable_documents(connection, settings)
    if requested_document_id is not None and not any(document.id == requested_document_id for document in documents):
        raise RagError(422, "DOCUMENT_HAS_NO_TEXT", "Tanlangan hujjat indexlash uchun tayyor emas.")
    if not documents:
        raise RagError(422, "NO_INDEXABLE_DOCUMENTS", "Indexlash uchun tayyor hujjatlar topilmadi.")

    chunks = build_chunks_for_documents(settings, documents)
    if not chunks:
        raise RagError(422, "NO_INDEXABLE_DOCUMENTS", "Indexlash uchun tayyor hujjatlar topilmadi.")

    try:
        with active_model.session():
            vectors = build_embeddings(active_model, chunks, settings.embedding_batch_size)
    except RagError:
        raise
    except Exception as exc:
        raise RagError(500, "VECTOR_INDEX_BUILD_ERROR", "Embedding batchlarini hisoblash muvaffaqiyatsiz tugadi.") from exc

    store = FaissStore()
    new_state: VectorIndexStateSnapshot | None = None
    try:
        with connection_scope(settings) as connection:
            connection.execute("BEGIN;")
            try:
                clear_chunks(connection)
                chunk_ids = replace_all_chunks(connection, chunks)
                index = store.create(settings.embedding_dimension)
                store.add(index, vectors, np.asarray(chunk_ids, dtype=np.int64))

                build_dir.mkdir(parents=True, exist_ok=False)
                store.write(index, index_part)
                _fsync_file(index_part)
                os.replace(index_part, _index_path(build_dir))
                manifest = VectorIndexManifest(
                    format_version=1,
                    generation_id=generation_id,
                    embedding_model=settings.embedding_model_name,
                    embedding_dimension=settings.embedding_dimension,
                    metric="cosine",
                    faiss_index_type="IndexIDMap2(IndexFlatIP)",
                    chunk_size_chars=settings.chunk_size_chars,
                    chunk_overlap_chars=settings.chunk_overlap_chars,
                    chunk_min_chars=settings.chunk_min_chars,
                    document_count=len(documents),
                    chunk_count=len(chunk_ids),
                    created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                )
                _write_manifest(_manifest_path(build_dir), manifest)
                parsed_manifest = _read_manifest(_manifest_path(build_dir))
                reloaded_index = store.read(_index_path(build_dir))
                if (
                    parsed_manifest.chunk_count != len(chunk_ids)
                    or parsed_manifest.embedding_dimension != settings.embedding_dimension
                    or int(reloaded_index.ntotal) != len(chunk_ids)
                    or reloaded_index.d != settings.embedding_dimension
                ):
                    raise RagError(500, "VECTOR_INDEX_BUILD_ERROR", "Yangi vector index artifacti yaroqsiz holatda yaratildi.")
                os.replace(build_dir, final_dir)

                document_ids = {chunk.document_id for chunk in chunks}
                connection.execute("UPDATE documents SET indexed = 0;")
                if document_ids:
                    placeholders = ",".join("?" for _ in document_ids)
                    connection.execute(
                        f"UPDATE documents SET indexed = 1 WHERE id IN ({placeholders});",
                        tuple(sorted(document_ids)),
                    )
                connection.execute(
                    """
                    UPDATE vector_index_state
                    SET active_generation = ?,
                        status = 'ready',
                        embedding_model = ?,
                        embedding_dimension = ?,
                        chunk_count = ?,
                        document_count = ?,
                        dirty = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1;
                    """,
                    (
                        generation_id,
                        settings.embedding_model_name,
                        settings.embedding_dimension,
                        len(chunk_ids),
                        len(documents),
                    ),
                )
                connection.commit()
                generation_committed = True
                new_state = _load_state(connection)
            except RagError:
                connection.rollback()
                raise
            except OSError as exc:
                connection.rollback()
                raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector index artifactlarini saqlab bo'lmadi.") from exc
            except sqlite3.Error:
                connection.rollback()
                raise
            except Exception as exc:
                connection.rollback()
                raise RagError(500, "VECTOR_INDEX_BUILD_ERROR", "Vector indexni yaratishda kutilmagan xatolik yuz berdi.") from exc
    except RagError:
        raise
    except sqlite3.Error as exc:
        raise RagError(500, "DATABASE_ERROR", "Vector indexni saqlash uchun database yangilanmadi.") from exc
    finally:
        if owned_model:
            active_model.close()
        _cleanup_file(index_part)
        _cleanup_file(manifest_part)
        _cleanup_directory(build_dir)
        if not generation_committed:
            _cleanup_directory(final_dir)

    if new_state is None:
        raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector index holati aniqlanmadi.")
    _prune_generations(settings, new_state.active_generation)
    return new_state
