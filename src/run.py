# -*- coding: utf-8 -*-
"""Pipeline Day 06: ingest -> chunk (A/B) -> embed + Chroma -> truy xuất A/B/C -> trace, metric, phiếu audit.

Chạy từ thư mục gốc repo:  python -m src.run
Yêu cầu trước: python scripts/fetch_corpus.py (nếu thiếu data/raw) và python scripts/download_model.py.
Pipeline KHÔNG ghi đè nhãn thủ công (results/audit/*_labels.json).
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .audit import coherence_sheet, grounding_sheet, metadata_sheet
from .chunking import by_structure, fixed_size
from .embeddings import MODEL_ID, MODEL_REVISION, ONNX_SHA256, E5OnnxEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus
from .store import ChromaVectorStore

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
AUDIT = RESULTS / "audit"

# Cấu hình (chốt trước khi chạy benchmark — xem benchmark/README.md)
STRATEGIES = {
    "A": {"index": "A", "chunking": "fixed_size", "chunk_size": 500, "overlap": 50, "use_filter": False,
          "hypothesis": "Baseline cửa sổ cố định 500/50; dự đoán cắt ngang khoản/điểm làm giảm coherence và có thể tách evidence dài qua 2 chunk."},
    "B": {"index": "B", "chunking": "structure (Điều/Chương cứng, khoản/điểm mềm)", "chunk_size": 800, "overlap": 0, "use_filter": False,
          "hypothesis": "Chunk theo Điều/khoản giữ trọn ý; dự đoán coherence cao hơn A và Evidence Hit@3 không thấp hơn A."},
    "C": {"index": "B", "chunking": "giống B (dùng chung index B)", "chunk_size": 800, "overlap": 0, "use_filter": True,
          "hypothesis": "Lọc theo regulation loại chunk của văn bản khác ở câu có khái niệm trùng giữa 3 quy chế; dự đoán tăng Hit ở câu filter, không đổi câu không filter."},
}
METADATA_FIELDS = "document_id,source,page,location,regulation,doc_code,issued_year,chapter,article"


def chunk_stats(chunks) -> dict:
    lens = [len(c.text) for c in chunks]
    return {"n_chunks": len(chunks), "total_chars": sum(lens), "min": min(lens), "median": statistics.median(lens),
            "mean": round(statistics.mean(lens), 1), "max": max(lens)}


def exact_topk(query_vec, ids, vecs, metas, k, flt):
    sel = [i for i, m in enumerate(metas) if not flt or all(m.get(a) == b for a, b in flt.items())]
    M = np.asarray([vecs[i] for i in sel], dtype=np.float32)
    sims = M @ np.asarray(query_vec, dtype=np.float32)
    order = np.argsort(-sims)[:k]
    return [ids[sel[i]] for i in order]


def main() -> int:
    t_start = time.perf_counter()
    RESULTS.mkdir(exist_ok=True)
    AUDIT.mkdir(exist_ok=True)
    timings: dict[str, float] = {}
    print("=" * 70 + "\nDAY 06 · DATA INGESTION PIPELINE\n" + "=" * 70)

    # 1. Ingest
    t0 = time.perf_counter()
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages, ingest_log = load_corpus(manifest_path)
    content = [p for p in pages if p.metadata["is_content"]]
    timings["ingest_s"] = round(time.perf_counter() - t0, 3)
    (RESULTS / "ingest_log.json").write_text(json.dumps(ingest_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[1] units={len(pages)} content_units={len(content)} ({timings['ingest_s']}s)")
    for doc_id, d in ingest_log["documents"].items():
        print(f"    {doc_id}: {d['content_units']}/{d['units']} content, excluded={d['excluded_units']}")
    if len(content) < 30:
        raise SystemExit(f"Corpus chỉ có {len(content)} đơn vị nội dung (< 30)")

    # 2. Chunk
    t0 = time.perf_counter()
    chunks = {"A": [c for p in content for c in fixed_size(p, 500, 50)],
              "B": [c for p in content for c in by_structure(p, 800)]}
    timings["chunk_s"] = round(time.perf_counter() - t0, 3)
    stats = {k: chunk_stats(v) for k, v in chunks.items()}
    print(f"[2] chunks A={stats['A']['n_chunks']} B={stats['B']['n_chunks']} ({timings['chunk_s']}s)")

    # 3. Embed + store (+ kiểm tra nạp lại)
    t0 = time.perf_counter()
    embedder = E5OnnxEmbedder()
    timings["model_load_s"] = round(time.perf_counter() - t0, 3)
    for idx in ("A", "B"):  # số token theo tokenizer của model (kèm tiền tố "passage: ")
        ntok = [len(embedder.tokenizer.encode(f"passage: {c.text}").ids) for c in chunks[idx]]
        stats[idx].update({"total_tokens": sum(ntok), "mean_tokens": round(statistics.mean(ntok), 1), "max_tokens": max(ntok)})
    store = ChromaVectorStore(RESULTS / "chroma_db", model_slug="e5small")
    sync_log = {}
    for idx in ("A", "B"):
        t0 = time.perf_counter()
        sync_log[idx] = {"first_sync": store.sync(idx, chunks[idx], embedder.embed_documents)}
        timings[f"embed_store_{idx}_s"] = round(time.perf_counter() - t0, 3)
        t0 = time.perf_counter()
        sync_log[idx]["reload_same_version"] = store.sync(idx, chunks[idx], embedder.embed_documents)
        timings[f"reload_{idx}_s"] = round(time.perf_counter() - t0, 3)
        r = sync_log[idx]["reload_same_version"]
        assert r["after"] == len(chunks[idx]) and r["embedded_upserted"] == 0, "Nạp lại bị nhân đôi hoặc embed lại"
        print(f"[3] index {idx}: {sync_log[idx]['first_sync']} | reload: {r}")
    (RESULTS / "reload_check.json").write_text(json.dumps({
        "note": "Lần 1: sync() embed chunk mới/đổi và xóa chunk không còn tồn tại. Lần 2 (cùng phiên bản) phải có embedded_upserted=0 và after = số chunk.",
        "sync": sync_log}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4. Benchmark
    bench_path = ROOT / "benchmark" / "benchmark.json"
    questions = json.loads(bench_path.read_text(encoding="utf-8"))
    bench_sha = hashlib.sha256(bench_path.read_bytes()).hexdigest()
    print(f"[4] {len(questions)} câu, sha256={bench_sha[:12]}…")

    # 5. Truy xuất
    traces, summaries, exact_check = {}, {}, {}
    for s, cfg in STRATEGIES.items():
        t0 = time.perf_counter()
        ids, vecs, metas = store.all_vectors(cfg["index"])
        out, agree = [], 0
        for q in questions:
            qv = embedder.embed_query(q["question"])
            flt = q.get("filter") if cfg["use_filter"] else None
            hits = store.search(cfg["index"], qv, top_k=3, filters=flt)
            out.append(evaluate_query(q, hits, flt))
            agree += [h["chunk_id"] for h in hits] == exact_topk(qv, ids, vecs, metas, 3, flt)
        timings[f"query_{s}_s"] = round(time.perf_counter() - t0, 3)
        traces[s], summaries[s] = out, summarize(out)
        exact_check[s] = f"{agree}/{len(questions)}"
        (RESULTS / f"traces_strategy_{s}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        sm = summaries[s]
        print(f"[5] {s}: dev H@1 {sm['dev']['hit1']} H@3 {sm['dev']['hit3']} | test H@1 {sm['test']['hit1']} H@3 {sm['test']['hit3']} | HNSW==exact {exact_check[s]}")

    (RESULTS / "benchmark_summary.json").write_text(json.dumps({
        "benchmark_sha256": bench_sha, "metric_definition": "hit = đúng document_id + đúng trang/đơn vị gold + chứa đủ evidence (chuỗi con sau chuẩn hóa)",
        "strategies": summaries, "hnsw_top3_equals_exact_top3": exact_check, "chunk_stats": stats}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6. Experiment log
    with open(ROOT / "artifacts" / "experiment_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["strategy", "chunking", "chunk_size", "overlap", "metadata", "filter", "vectorizer", "vector_store", "hypothesis",
                    "n_chunks", "mean_chunk_chars", "dev_hit1", "dev_hit3", "test_hit1", "test_hit3",
                    "embed_store_s", "query_20q_s", "cost_usd", "notes"])
        for s, cfg in STRATEGIES.items():
            sm, st = summaries[s], stats[cfg["index"]]
            w.writerow([s, cfg["chunking"], cfg["chunk_size"], cfg["overlap"], METADATA_FIELDS,
                        "where regulation=<filter> chỉ với câu có filter" if cfg["use_filter"] else "none",
                        f"{MODEL_ID}@{MODEL_REVISION[:8]} (ONNX, 384-d, mean pooling, L2)",
                        f"chromadb {version('chromadb')} PersistentClient, cosine, HNSW; collection {store.collection_name(cfg['index'])}",
                        cfg["hypothesis"], st["n_chunks"], st["mean"], sm["dev"]["hit1"], sm["dev"]["hit3"], sm["test"]["hit1"], sm["test"]["hit3"],
                        timings[f"embed_store_{cfg['index']}_s"] if s != "C" else "0 (dùng index B)", timings[f"query_{s}_s"], 0,
                        f"filter-scope top3: dev {sm['dev']['top3_in_filter_scope']}, test {sm['test']['top3_in_filter_scope']}"])

    # 7. Phiếu audit (nhãn thủ công nằm ở *_labels.json, không bị ghi đè)
    docs = {d["document_id"]: d for d in manifest["documents"]}
    sheets = {
        "coherence_sheet.json": coherence_sheet(content, {"A": chunks["A"], "B": chunks["B"]}),
        "metadata_sheet.json": metadata_sheet(traces, pages, docs),
        "grounding_sheet.json": grounding_sheet(traces),
    }
    for name, rows in sheets.items():
        (AUDIT / name).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # 8. Run metadata
    timings["total_s"] = round(time.perf_counter() - t_start, 3)
    run_meta = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0], "platform": platform.platform(), "processor": platform.processor(),
        "packages": {p: version(p) for p in ("chromadb", "onnxruntime", "tokenizers", "pypdf", "numpy")},
        "embedding": {"model": MODEL_ID, "revision": MODEL_REVISION, "onnx_sha256": ONNX_SHA256, "dimensions": embedder.dimensions,
                      "max_length_tokens": embedder.max_length, "pooling": "mean + L2", "query_prefix": "query: ",
                      "document_prefix": "passage: ", "provider": "local ONNX Runtime (CPU)", "truncated_inputs": embedder.truncated_inputs},
        "vector_store": {"engine": "chromadb.PersistentClient", "path": "results/chroma_db", "space": "cosine", "index": "HNSW (approximate)",
                         "collections": {k: store.collection_name(k) for k in ("A", "B")}},
        "benchmark_sha256": bench_sha, "timings_s": timings, "cost_usd": 0.0,
        "cost_note": "Không gọi API trả phí; chỉ tốn CPU local và ~490 MB tải model một lần.",
    }
    (RESULTS / "run_metadata.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {timings['total_s']}s — kết quả trong results/, nhật ký trong artifacts/experiment_log.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
