# -*- coding: utf-8 -*-
"""Chấm truy xuất (Hit@1, Evidence Hit@3), lưu trace top-3 và tỷ lệ tuân thủ filter.

Định nghĩa hit (theo GUIDE): chunk thuộc đúng nguồn (document_id) + đúng trang/đơn vị gold
VÀ chứa ĐỦ evidence đã ghi (so khớp chuỗi con sau khi chuẩn hóa chữ thường, bỏ dấu câu, gộp khoảng trắng).
Không dùng so khớp một phần để tính hit; độ phủ evidence chỉ được ghi thêm để phân tích lỗi.
"""
from __future__ import annotations

import re
from typing import Any


def match_key(text: str) -> str:
    t = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def evidence_coverage(chunk_text: str, evidence: str) -> float:
    """Tỷ lệ từ của evidence có mặt trong chunk (chỉ để phân tích, không dùng để tính hit)."""
    ev = match_key(evidence).split()
    if not ev:
        return 0.0
    chunk_words = set(match_key(chunk_text).split())
    return round(sum(1 for w in ev if w in chunk_words) / len(ev), 3)


def gold_pages(question: dict[str, Any]) -> set[int]:
    g = question["gold_page"]
    return {int(x) for x in g} if isinstance(g, list) else {int(g)}


def is_chunk_hit(hit: dict[str, Any], question: dict[str, Any]) -> bool:
    meta = hit["metadata"]
    if meta.get("document_id") != question["gold_source_id"]:
        return False
    if int(meta.get("page", -1)) not in gold_pages(question):
        return False
    return match_key(question["evidence_quote"]) in match_key(hit["text"])


def filter_compliant(hits: list[dict[str, Any]], flt: dict[str, Any] | None) -> bool | None:
    """True nếu mọi chunk trong top-k thỏa filter; None nếu câu không có filter."""
    if not flt:
        return None
    return all(all(h["metadata"].get(k) == v for k, v in flt.items()) for h in hits)


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]], applied_filter: dict[str, Any] | None) -> dict[str, Any]:
    annotated = []
    for h in hits:
        m = h["metadata"]
        annotated.append(
            {
                "rank": h["rank"],
                "chunk_id": h["chunk_id"],
                "score": h["score"],
                "document_id": m.get("document_id"),
                "page": m.get("page"),
                "location": m.get("location"),
                "regulation": m.get("regulation"),
                "article": m.get("article"),
                "is_gold_location": m.get("document_id") == question["gold_source_id"] and int(m.get("page", -1)) in gold_pages(question),
                "is_hit": is_chunk_hit(h, question),
                "evidence_coverage": evidence_coverage(h["text"], question["evidence_quote"]),
                "text": h["text"],
                "metadata": {k: v for k, v in m.items() if k not in ("chunk_id",)},
            }
        )
    return {
        "id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "context": question.get("context"),
        "expected_answer": question.get("expected_answer"),
        "gold_source_id": question["gold_source_id"],
        "gold_page": question["gold_page"],
        "gold_location": question.get("gold_location"),
        "gold_article": question.get("gold_article"),
        "evidence_quote": question["evidence_quote"],
        "question_filter": question.get("filter"),
        "applied_filter": applied_filter,
        "hit_at_1": bool(annotated and annotated[0]["is_hit"]),
        "evidence_hit_at_3": any(a["is_hit"] for a in annotated[:3]),
        "gold_location_in_top3": any(a["is_gold_location"] for a in annotated[:3]),
        "top3_in_filter_scope": filter_compliant(hits[:3], question.get("filter")),
        "top_hits": annotated,
    }


def _stats(traces: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(traces)
    h1 = sum(t["hit_at_1"] for t in traces)
    h3 = sum(t["evidence_hit_at_3"] for t in traces)
    gl = sum(t["gold_location_in_top3"] for t in traces)
    fq = [t for t in traces if t["question_filter"]]
    fc = sum(1 for t in fq if t["top3_in_filter_scope"])
    return {
        "n": n,
        "hit1": f"{h1}/{n}", "hit1_count": h1, "hit1_rate": round(h1 / n, 4) if n else None,
        "hit3": f"{h3}/{n}", "hit3_count": h3, "hit3_rate": round(h3 / n, 4) if n else None,
        "gold_location_in_top3": f"{gl}/{n}",
        "filter_questions": len(fq),
        "top3_in_filter_scope": f"{fc}/{len(fq)}" if fq else "N/A",
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dev": _stats([t for t in traces if t["split"] == "dev"]),
        "test": _stats([t for t in traces if t["split"] == "test"]),
        "overall": _stats(traces),
    }
