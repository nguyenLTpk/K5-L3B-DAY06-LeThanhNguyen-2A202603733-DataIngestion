# -*- coding: utf-8 -*-
"""Tạo PHIẾU chấm thủ công (sheet) từ chunk và trace. File sheet được sinh lại mỗi lần chạy;
nhãn thủ công nằm ở file *_labels.json riêng mà pipeline KHÔNG ghi đè.

Quy tắc chọn mẫu được cố định trong code trước khi xem kết quả:
- Coherence: 10 đơn vị nội dung cách đều nhau theo thứ tự corpus (chỉ số round(i*(n-1)/9)),
  vị trí = ký tự giữa đơn vị. Mỗi chiến lược chấm chunk chứa vị trí đó (A: chunk bắt đầu sớm nhất).
- Metadata & grounding: 5 câu test x top-3 cho A/B/C.
"""
from __future__ import annotations

from typing import Any

from .models import Chunk, DocumentPage


def coherence_positions(content_pages: list[DocumentPage], k: int = 10) -> list[dict[str, Any]]:
    n = len(content_pages)
    idxs = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    out = []
    for j, i in enumerate(idxs, start=1):
        p = content_pages[i]
        off = len(p.text) // 2
        out.append({"position_id": f"pos{j:02d}", "document_id": p.document_id, "location": p.location, "page": p.page,
                    "offset": off, "source_context": p.text[max(0, off - 80): off + 80]})
    return out


def covering_chunk(chunks: list[Chunk], pos: dict[str, Any]) -> Chunk | None:
    cands = [c for c in chunks if c.document_id == pos["document_id"] and c.page == pos["page"]
             and c.metadata["start_char"] <= pos["offset"] < c.metadata["end_char"]]
    return min(cands, key=lambda c: c.metadata["start_char"]) if cands else None


def coherence_sheet(content_pages, chunks_by_strategy: dict[str, list[Chunk]]) -> list[dict[str, Any]]:
    rows = []
    for pos in coherence_positions(content_pages):
        row = dict(pos)
        for s, chunks in chunks_by_strategy.items():
            c = covering_chunk(chunks, pos)
            row[f"strategy_{s}"] = {"chunk_id": c.chunk_id, "article": c.metadata["article"], "length": len(c.text), "text": c.text} if c else None
        rows.append(row)
    return rows


def metadata_sheet(traces_by_strategy: dict[str, list[dict[str, Any]]], pages: list[DocumentPage], manifest_docs: dict[str, dict]) -> list[dict[str, Any]]:
    by_loc = {(p.document_id, p.page): p for p in pages}
    rows = []
    for s, traces in traces_by_strategy.items():
        for t in traces:
            if t["split"] != "test":
                continue
            for h in t["top_hits"]:
                m = h["metadata"]
                src = by_loc.get((m["document_id"], m["page"]))
                doc = manifest_docs[m["document_id"]]
                text_at_offsets = src.text[m["start_char"]:m["end_char"]] if src else None
                rows.append({
                    "strategy": s, "question_id": t["id"], "rank": h["rank"], "chunk_id": h["chunk_id"],
                    "document_id": m["document_id"], "source": m["source"], "page": m["page"], "location": m["location"],
                    "regulation": m["regulation"], "doc_code": m["doc_code"], "issued_year": m["issued_year"],
                    "chapter": m["chapter"], "article": m["article"], "articles_covered": m["articles_covered"],
                    "auto_check": {
                        "required_fields_present": all(m.get(f) not in (None, "") for f in ("document_id", "source", "page", "regulation")),
                        "text_matches_source_at_offsets": text_at_offsets == h["text"],
                        "doc_fields_match_manifest": (m["regulation"], m["doc_code"], m["issued_year"], m["source"]) ==
                                                     (doc["regulation"], doc["doc_code"], int(doc["issued_year"]), doc["path"]),
                    },
                    "chunk_head": h["text"][:220],
                })
    return rows


def grounding_sheet(traces_by_strategy: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    test_ids = [t["id"] for t in next(iter(traces_by_strategy.values())) if t["split"] == "test"]
    for qid in test_ids:
        base = next(t for t in next(iter(traces_by_strategy.values())) if t["id"] == qid)
        row = {"question_id": qid, "question": base["question"], "expected_answer": base["expected_answer"],
               "gold": f"{base['gold_source_id']}:{base['gold_location']}", "evidence_quote": base["evidence_quote"]}
        for s, traces in traces_by_strategy.items():
            t = next(x for x in traces if x["id"] == qid)
            row[f"strategy_{s}"] = {
                "applied_filter": t["applied_filter"], "evidence_hit_at_3_auto": t["evidence_hit_at_3"],
                "top3": [{"rank": h["rank"], "loc": f"{h['document_id']}:{h['location']}", "article": h["article"], "text": h["text"]} for h in t["top_hits"]],
            }
        rows.append(row)
    return rows
