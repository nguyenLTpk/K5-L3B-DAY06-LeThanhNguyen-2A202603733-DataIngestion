# -*- coding: utf-8 -*-
"""Vector store: ChromaDB PersistentClient (lưu trên đĩa), cosine, filter metadata bằng `where`.

- Mỗi cấu hình chunking có một collection riêng; C dùng CHUNG collection với B, chỉ thêm `where`.
- `sync()` idempotent: ID chunk ổn định -> nạp lại không nhân đôi; chunk đổi nội dung hoặc metadata
  (content_sha1 = hash text + metadata khác) được ghi lại; chunk không còn trong corpus (tài liệu đổi/xóa)
  bị xóa khỏi collection.
- Chroma dùng chỉ mục HNSW (tìm kiếm xấp xỉ); run.py đối chiếu với tìm kiếm chính xác bằng numpy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import chromadb
from chromadb.config import Settings

from .models import Chunk


class ChromaVectorStore:
    def __init__(self, persist_dir: Path, model_slug: str) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir), settings=Settings(anonymized_telemetry=False))
        self.model_slug = model_slug

    def collection_name(self, index: str) -> str:
        return f"day06_{index.lower()}_{self.model_slug}"

    def collection(self, index: str):
        return self.client.get_or_create_collection(
            name=self.collection_name(index),
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # vector do E5OnnxEmbedder tạo, Chroma không tự embed
        )

    def sync(self, index: str, chunks: list[Chunk], embed_fn: Callable[[list[str]], list[list[float]]]) -> dict[str, int]:
        col = self.collection(index)
        existing = col.get(include=["metadatas"])
        old = {i: (m or {}).get("content_sha1") for i, m in zip(existing["ids"], existing["metadatas"])}
        new_ids = {c.chunk_id for c in chunks}
        if len(new_ids) != len(chunks):
            raise ValueError("chunk_id bị trùng trong cùng một cấu hình")

        stale = [i for i in old if i not in new_ids]
        if stale:
            col.delete(ids=stale)
        todo = [c for c in chunks if old.get(c.chunk_id) != c.metadata["content_sha1"]]
        if todo:
            vectors = embed_fn([c.text for c in todo])
            if len(vectors) != len(todo):
                raise ValueError("Số vector không khớp số chunk")
            for i in range(0, len(todo), 128):
                part = todo[i:i + 128]
                col.upsert(
                    ids=[c.chunk_id for c in part],
                    embeddings=vectors[i:i + 128],
                    documents=[c.text for c in part],
                    metadatas=[c.metadata for c in part],
                )
        return {"before": len(old), "deleted_stale": len(stale), "embedded_upserted": len(todo),
                "unchanged": len(chunks) - len(todo), "after": col.count()}

    def search(self, index: str, query_vector: list[float], top_k: int = 3, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        col = self.collection(index)
        where = None
        if filters:
            conds = [{k: v} for k, v in filters.items() if v is not None]
            where = conds[0] if len(conds) == 1 else {"$and": conds}
        res = col.query(query_embeddings=[query_vector], n_results=top_k, where=where,
                        include=["documents", "metadatas", "distances"])
        return [
            {"rank": r + 1, "chunk_id": cid, "text": doc, "score": round(1.0 - float(dist), 4), "metadata": meta}
            for r, (cid, doc, meta, dist) in enumerate(zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]))
        ]

    def all_vectors(self, index: str) -> tuple[list[str], list[list[float]], list[dict[str, Any]]]:
        got = self.collection(index).get(include=["embeddings", "metadatas"])
        return got["ids"], got["embeddings"], got["metadatas"]
