# -*- coding: utf-8 -*-
"""Kiểm thử xử lý tài liệu thay đổi trên một Chroma TẠM (không đụng results/chroma_db).

Kịch bản: nạp các chunk thật (B) của tt16-2015:u05 -> nạp lại y nguyên -> mô phỏng tài liệu đổi (1 chunk sửa nội dung, 1 chunk bị xóa).
Kỳ vọng: không nhân đôi; chunk sửa được embed lại; chunk bị xóa không còn trong collection.
Chạy: python scripts/test_store_sync.py  -> results/store_sync_test.json
"""
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.chunking import by_structure  # noqa: E402
from src.embeddings import E5OnnxEmbedder  # noqa: E402
from src.ingestion import load_corpus  # noqa: E402
from src.store import ChromaVectorStore  # noqa: E402


def main() -> int:
    pages, _ = load_corpus(ROOT / "data" / "manifest.json")
    p = next(x for x in pages if x.document_id == "tt16-2015" and x.page == 5)
    chunks = by_structure(p)[:6] if len(by_structure(p)) >= 6 else by_structure(p)
    emb = E5OnnxEmbedder()
    # Windows giữ khóa file HNSW của Chroma đến khi tiến trình kết thúc -> bỏ qua lỗi dọn thư mục tạm
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = ChromaVectorStore(Path(tmp), model_slug="synctest")
        steps = {"1_first_load": store.sync("T", chunks, emb.embed_documents),
                 "2_reload_same": store.sync("T", chunks, emb.embed_documents)}
        changed = copy.deepcopy(chunks)
        changed[0].text += " (sửa đổi mô phỏng)"
        changed[0].metadata["content_sha1"] = hashlib.sha1(changed[0].text.encode()).hexdigest()
        removed_id = changed.pop()  # chunk cuối biến mất khỏi tài liệu mới
        steps["3_document_changed"] = store.sync("T", changed, emb.embed_documents)
        ids = set(store.collection("T").get()["ids"])
        result = {
            "n_chunks_initial": len(chunks), "steps": steps,
            "removed_chunk_gone": removed_id.chunk_id not in ids,
            "no_duplicates": len(ids) == len(changed),
            "pass": steps["2_reload_same"]["embedded_upserted"] == 0 and steps["3_document_changed"]["deleted_stale"] == 1
                    and steps["3_document_changed"]["embedded_upserted"] == 1 and removed_id.chunk_id not in ids,
        }
        (ROOT / "results" / "store_sync_test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        del store
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
