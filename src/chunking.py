# -*- coding: utf-8 -*-
"""Chiến lược A (cửa sổ cố định) và B (theo cấu trúc Điều/khoản), giữ metadata truy vết.

Cả hai chiến lược chunk trong phạm vi TỪNG đơn vị nguồn (trang PDF / đơn vị HTML) để `page` luôn chính xác.
Hệ quả: một Điều kéo dài qua hai trang bị tách ở ranh giới trang (ghi nhận là giới hạn).
"""
from __future__ import annotations

import hashlib
import json
import re

from .ingestion import ARTICLE_RE, CHAPTER_RE, state_at
from .models import Chunk, DocumentPage


def _articles_in_range(page: DocumentPage, start: int, end: int) -> list[str]:
    arts = []
    first = state_at(page, start).get("article")
    if first:
        arts.append(first)
    for m in page.metadata.get("markers", []):
        if start < m["offset"] < end and m.get("article") and m["article"] not in arts:
            arts.append(m["article"])
    return arts


def _make_chunk(page: DocumentPage, text: str, start: int, end: int, idx: int, tag: str, chunk_type: str) -> Chunk:
    st = state_at(page, start)
    arts = _articles_in_range(page, start, end)
    # chunk bắt đầu bằng tiêu đề Chương (chưa có Điều) -> gán Điều đầu tiên xuất hiện trong chunk
    article = st.get("article") or (arts[0] if arts else "")
    meta = {
        "document_id": page.document_id,
        "source": page.source,
        "page": page.page,
        "location": page.location,
        "location_type": page.metadata["location_type"],
        "printed_page": page.metadata.get("printed_page") or -1,
        "regulation": page.metadata["regulation"],
        "doc_code": page.metadata["doc_code"],
        "issued_year": page.metadata["issued_year"],
        "chapter": st.get("chapter") or "",
        "article": article,
        "articles_covered": "; ".join(arts),
        "start_char": start,
        "end_char": end,
        "length": len(text),
        "chunk_type": chunk_type,
    }
    # hash trên text + metadata: đổi nội dung HOẶC metadata đều khiến sync() ghi lại bản ghi
    meta["content_sha1"] = hashlib.sha1((text + json.dumps(meta, ensure_ascii=False, sort_keys=True)).encode("utf-8")).hexdigest()
    return Chunk(
        chunk_id=f"{page.document_id}:{page.location}:{tag}{idx:02d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=meta,
    )


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Strategy A: cửa sổ ký tự cố định có overlap, không quan tâm ranh giới câu/Điều."""
    text = page.text
    if not text.strip():
        return []
    step = max(1, size - overlap)
    chunks, start, idx = [], 0, 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end]
        if piece.strip():
            chunks.append(_make_chunk(page, piece, start, end, idx, "fix", "fixed_size"))
            idx += 1
        if end >= len(text):
            break
        start += step
    return chunks


def _is_heading(line: str) -> bool:
    return bool(CHAPTER_RE.match(line)) or (line.isupper() and len(line) > 3) or line.startswith("(Ban hành")


def _split_long(line: str, max_size: int) -> list[str]:
    """Tách một dòng quá dài theo ranh giới câu/vế (". " hoặc "; "), mỗi phần <= max_size nếu có thể."""
    parts = re.split(r"(?<=[.;])\s+", line)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > max_size:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out


def by_structure(page: DocumentPage, max_size: int = 800) -> list[Chunk]:
    """Strategy B: ranh giới cứng tại Chương/Điều, ranh giới mềm tại khoản/điểm; gộp đến max_size ký tự.

    Tiêu đề Chương / tiêu đề in hoa được gắn vào chunk của Điều ngay sau nó thay vì đứng riêng.
    """
    text = page.text
    if not text.strip():
        return []
    # (offset, line) cho từng dòng cấu trúc; dòng quá dài được tách thành nhiều mảnh
    lines: list[tuple[int, str]] = []
    off = 0
    for ln in text.split("\n"):
        if len(ln) > max_size:
            pos = off
            for piece in _split_long(ln, max_size):
                i = text.find(piece, pos)
                lines.append((i, piece))
                pos = i + len(piece)
        elif ln:
            lines.append((off, ln))
        off += len(ln) + 1

    groups: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    cur_len = 0
    for o, ln in lines:
        hard = bool(ARTICLE_RE.match(ln)) or bool(CHAPTER_RE.match(ln)) or ln in ("QUY CHẾ", "PHỤ LỤC", "THÔNG TƯ")
        only_headings = cur and all(_is_heading(x) for _, x in cur)
        if cur and ((hard and not only_headings) or cur_len + 1 + len(ln) > max_size):
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append((o, ln))
        cur_len += len(ln) + (1 if cur_len else 0)
    if cur:
        groups.append(cur)

    chunks = []
    for idx, g in enumerate(groups):
        start = g[0][0]
        end = g[-1][0] + len(g[-1][1])
        chunks.append(_make_chunk(page, text[start:end], start, end, idx, "st", "structure"))
    return chunks
