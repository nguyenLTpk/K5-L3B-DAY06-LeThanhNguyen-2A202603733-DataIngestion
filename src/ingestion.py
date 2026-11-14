# -*- coding: utf-8 -*-
"""Đọc PDF/HTML, chuẩn hóa Unicode, sửa lỗi trích xuất và ghi log theo từng đơn vị nguồn.

Đơn vị nguồn:
- PDF: mỗi trang vật lý là một đơn vị (location = "p<số trang>").
- HTML (không có phân trang): chia theo thứ tự thành các đơn vị >= 1.500 ký tự đã chuẩn hóa,
  cắt tại ranh giới dòng (location = "u01", "u02", ...).
"""
from __future__ import annotations

import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pypdf

from .models import DocumentPage

ROOT = Path(__file__).resolve().parents[1]
MIN_HTML_UNIT_CHARS = 1500

# Dòng bắt đầu một khối cấu trúc của văn bản pháp luật -> không nối với dòng trước.
STRUCT_START = re.compile(
    r"^(Chương\s+[IVXLC]+\b|Điều\s+\d+\s*\.|\d+\.\s|[a-zđ]\)\s|-\s|\(Ban hành|QUY CHẾ$|THÔNG TƯ$)"
)
ARTICLE_RE = re.compile(r"^Điều\s+(\d+)\s*\.\s*(.*)$")
CHAPTER_RE = re.compile(r"^Chương\s+([IVXLC]+)\b")
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


# --------------------------------------------------------------------------- HTML
class _HTMLText(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "table", "td", "th"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    return "".join(parser.parts)


# ---------------------------------------------------------------------- normalize
def _basic_clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("\t", " ").replace("​", "")
    text = re.sub(r"[ ]+", " ", text)
    return text


# caselaw.vn tự viết hoa một số từ khi gắn liên kết ("bảo đảm Điều kiện", "bảng Điểm", "chi Tiết").
# Văn phong pháp lý viết thường các từ này giữa câu; "Điều"/"Mục" + số (ví dụ "Điều 14") được giữ nguyên.
_CASE_ARTIFACT = re.compile(r"(?<=[a-zà-ỹđ,;:] )(Điểm|Khoản|Tiết|Điều(?! \d)|Mục(?! \d))")
# Phần giao diện trang web lọt vào khối nội dung (tab "Nội dung VB / Văn bản gốc / ... đăng nhập")
_SITE_CHROME = re.compile(r"\nNội dung VB\nVăn bản gốc\n.*$", re.S)


def fix_case_artifacts(text: str) -> tuple[str, int]:
    return _CASE_ARTIFACT.subn(lambda m: m.group(1).lower(), text)


def strip_site_chrome(text: str) -> tuple[str, int]:
    new = _SITE_CHROME.sub("", text)
    return new, len(text) - len(new)


def _tidy_spaces(line: str) -> str:
    line = re.sub(r"\s+([,.;:!?)])", r"\1", line)
    line = re.sub(r"\(\s+", "(", line)
    line = re.sub(r"\s{2,}", " ", line)
    return line.strip()


def build_vocab(texts: list[str]) -> set[str]:
    """Từ điển âm tiết (chữ thường) lấy từ văn bản tham chiếu sạch (HTML)."""
    vocab: set[str] = set()
    for t in texts:
        vocab.update(w.lower() for w in WORD_RE.findall(unicodedata.normalize("NFC", t)))
    return vocab


_TOKEN_RE = re.compile(r"^([^\W\d_]+)([^\w\s]*)$")  # chữ cái + dấu câu đuôi (nếu có)


def _split_token(tok: str) -> tuple[str, str]:
    """Trả về (phần chữ cái, dấu câu đuôi); ('', '') nếu token có số hoặc dấu câu đầu."""
    m = _TOKEN_RE.match(tok)
    return (m.group(1), m.group(2)) if m else ("", "")


def repair_split_syllables(line: str, vocab: set[str]) -> tuple[str, int]:
    """Gộp mảnh âm tiết bị PDF chèn khoảng trắng, ví dụ 'đà o' -> 'đào', 'Điề u' -> 'Điều'.

    Chỉ gộp khi (1) một token chữ cái không có trong từ điển âm tiết và (2) phép nối với
    token kề (ưu tiên phải, sau đó trái) tạo ra âm tiết có trong từ điển. Không gộp qua dấu câu.
    Trường hợp cả hai mảnh đều là âm tiết hợp lệ (ví dụ 'khó a') không sửa được -> ghi nhận là giới hạn.
    """
    if not vocab:
        return line, 0
    toks = line.split(" ")
    repairs = 0
    i = 0
    while i < len(toks):
        core, punct = _split_token(toks[i])
        if core and core.lower() not in vocab:
            if i + 1 < len(toks) and not punct:  # gộp phải
                n_core, _ = _split_token(toks[i + 1])
                if n_core and (core + n_core).lower() in vocab:
                    toks[i] = toks[i] + toks[i + 1]
                    del toks[i + 1]
                    repairs += 1
                    continue
            if i > 0:  # gộp trái
                p_core, p_punct = _split_token(toks[i - 1])
                if p_core and not p_punct and (p_core + core).lower() in vocab:
                    toks[i - 1] = toks[i - 1] + toks[i]
                    del toks[i]
                    repairs += 1
                    i -= 1
                    continue
        i += 1
    return " ".join(toks), repairs


def normalize_text(text: str, vocab: set[str] | None = None, join_wrapped_lines: bool = False) -> tuple[str, dict[str, int]]:
    """Chuẩn hóa NFC + khoảng trắng; tùy chọn nối dòng bị ngắt cứng (PDF) và sửa âm tiết tách rời.

    Trả về (text, stats). Mỗi dòng của kết quả là một khối cấu trúc (Chương/Điều/khoản/điểm/đoạn).
    """
    stats = {"lines_in": 0, "lines_joined": 0, "syllable_repairs": 0}
    text = _basic_clean(text)
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not re.fullmatch(r"-{3,}", ln)]
    stats["lines_in"] = len(lines)

    paragraphs: list[str] = []
    for ln in lines:
        if join_wrapped_lines and paragraphs:
            prev = paragraphs[-1]
            prev_is_heading = bool(CHAPTER_RE.match(prev)) or (prev.isupper() and len(prev) > 3)
            starts_block = bool(STRUCT_START.match(ln)) or (ln.isupper() and len(ln) > 3)
            if not starts_block and not prev_is_heading:
                paragraphs[-1] = prev + " " + ln
                stats["lines_joined"] += 1
                continue
        paragraphs.append(ln)

    out: list[str] = []
    for p in paragraphs:
        p = _tidy_spaces(p)
        if vocab:
            p, n = repair_split_syllables(p, vocab)
            stats["syllable_repairs"] += n
            p = _tidy_spaces(p)
        out.append(p)
    return "\n".join(out).strip(), stats


def oov_rate(text: str, vocab: set[str]) -> float:
    words = [w.lower() for w in WORD_RE.findall(text)]
    if not words or not vocab:
        return 0.0
    return round(sum(1 for w in words if w not in vocab) / len(words), 4)


# ------------------------------------------------------------- structure tracking
def structure_markers(text: str, state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ghi vị trí (offset) của các tiêu đề Chương/Điều trong text; state mang sang đơn vị kế tiếp.

    state = {"part": "thong_tu"|"quy_che", "chapter": "Chương II"|None, "article": "Điều 5"|None, "article_title": str}
    """
    markers: list[dict[str, Any]] = []
    offset = 0
    for line in text.split("\n"):
        if line.strip() == "QUY CHẾ":
            state = {**state, "part": "quy_che", "chapter": None, "article": None, "article_title": ""}
        cm = CHAPTER_RE.match(line)
        am = ARTICLE_RE.match(line)
        if cm:  # sang Chương mới: chưa thuộc Điều nào cho đến tiêu đề Điều kế tiếp
            state = {**state, "chapter": f"Chương {cm.group(1)}", "article": None, "article_title": ""}
            markers.append({"offset": offset, **state})
        elif am:
            label = f"Điều {am.group(1)}" + (" (Thông tư)" if state.get("part") == "thong_tu" else "")
            state = {**state, "article": label, "article_title": am.group(2)[:120]}
            markers.append({"offset": offset, **state})
        offset += len(line) + 1
    return markers, state


def state_at(page: DocumentPage, offset: int) -> dict[str, Any]:
    st = page.metadata.get("start_state", {})
    for m in page.metadata.get("markers", []):
        if m["offset"] <= offset:
            st = m
        else:
            break
    return st


# -------------------------------------------------------------------- loaders
def _doc_meta(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_code": doc["doc_code"],
        "regulation": doc["regulation"],
        "issued_year": int(doc["issued_year"]),
        "source_url": doc["source_url"],
    }


def load_pdf(path: Path, doc: dict[str, Any], vocab: set[str]) -> tuple[list[DocumentPage], list[dict[str, Any]]]:
    reader = pypdf.PdfReader(str(path))
    pages: list[DocumentPage] = []
    log: list[dict[str, Any]] = []
    state: dict[str, Any] = {"part": doc.get("initial_part", "quy_che"), "chapter": None, "article": None, "article_title": ""}
    min_chars = int(doc.get("min_content_chars", 300))
    for idx, page_obj in enumerate(reader.pages):
        no = idx + 1
        entry: dict[str, Any] = {"document_id": doc["document_id"], "location": f"p{no}"}
        try:
            raw = page_obj.extract_text() or ""
        except Exception as exc:  # ghi lỗi, không dừng pipeline
            raw = ""
            entry["error"] = f"extract_text failed: {exc!r}"
        raw_clean = _basic_clean(raw).strip()
        # dòng đầu là số trang in (ví dụ "1") -> giữ làm metadata, bỏ khỏi nội dung
        printed = None
        m = re.match(r"^(\d{1,3})\s*\n", raw_clean)
        if m:
            printed = int(m.group(1))
            raw_clean = raw_clean[m.end():]
        text, stats = normalize_text(raw_clean, vocab=vocab, join_wrapped_lines=True)
        n_images = len(page_obj.images) if hasattr(page_obj, "images") else 0
        is_content = len(text) >= min_chars
        markers, new_state = structure_markers(text, state)
        entry.update(
            {
                "printed_page": printed,
                "raw_chars": len(raw),
                "normalized_chars": len(text),
                "images": n_images,
                "is_content": is_content,
                "oov_rate_before_repair": oov_rate(normalize_text(raw_clean, None, True)[0], vocab),
                "oov_rate_after_repair": oov_rate(text, vocab),
                **stats,
            }
        )
        if not text:
            entry["warning"] = "trang rỗng sau trích xuất (trang scan/ảnh, không OCR) -> không tính là trang nội dung"
        elif not is_content:
            entry["warning"] = f"dưới {min_chars} ký tự -> không tính là trang nội dung"
        log.append(entry)
        pages.append(
            DocumentPage(
                document_id=doc["document_id"],
                source=doc["path"],
                page=no,
                text=text,
                metadata={
                    **_doc_meta(doc),
                    "location": f"p{no}",
                    "location_type": "pdf_page",
                    "printed_page": printed,
                    "is_content": is_content,
                    "start_state": state,
                    "markers": markers,
                },
            )
        )
        state = new_state
    return pages, log


def load_html(path: Path, doc: dict[str, Any], vocab: set[str] | None = None) -> tuple[list[DocumentPage], list[dict[str, Any]]]:
    html = path.read_text(encoding="utf-8")
    text, stats = normalize_text(html_to_text(html), vocab=None, join_wrapped_lines=False)
    text, stats["site_chrome_chars_removed"] = strip_site_chrome(text)
    text, stats["case_artifacts_fixed"] = fix_case_artifacts(text)
    lines = text.split("\n")
    # chia theo thứ tự thành đơn vị >= MIN_HTML_UNIT_CHARS, cắt tại ranh giới dòng
    units: list[list[str]] = [[]]
    for ln in lines:
        units[-1].append(ln)
        if len("\n".join(units[-1])) >= MIN_HTML_UNIT_CHARS:
            units.append([])
    if not units[-1]:
        units.pop()
    if len(units) > 1 and len("\n".join(units[-1])) < MIN_HTML_UNIT_CHARS:
        units[-2].extend(units.pop())  # gộp phần đuôi ngắn vào đơn vị trước

    pages: list[DocumentPage] = []
    log: list[dict[str, Any]] = []
    state: dict[str, Any] = {"part": doc.get("initial_part", "thong_tu"), "chapter": None, "article": None, "article_title": ""}
    for i, ulines in enumerate(units, start=1):
        utext = "\n".join(ulines)
        loc = f"u{i:02d}"
        markers, new_state = structure_markers(utext, state)
        log.append(
            {
                "document_id": doc["document_id"],
                "location": loc,
                "normalized_chars": len(utext),
                "first_line": ulines[0][:80],
                "is_content": True,
            }
        )
        pages.append(
            DocumentPage(
                document_id=doc["document_id"],
                source=doc["path"],
                page=i,
                text=utext,
                metadata={
                    **_doc_meta(doc),
                    "location": loc,
                    "location_type": "html_unit",
                    "printed_page": None,
                    "is_content": True,
                    "start_state": state,
                    "markers": markers,
                },
            )
        )
        state = new_state
    if log:
        log[0]["html_normalize_stats"] = stats
    return pages, log


def load_corpus(manifest_path: Path) -> tuple[list[DocumentPage], dict[str, Any]]:
    """Đọc toàn bộ corpus theo manifest. Trả về (danh sách đơn vị, ingest log)."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # từ điển âm tiết: các nguồn HTML sạch (văn bản tham chiếu + các văn bản HTML của corpus)
    vocab_texts = []
    for ref in manifest.get("normalization_reference", []):
        vocab_texts.append(html_to_text((ROOT / ref["path"]).read_text(encoding="utf-8")))
    for d in manifest["documents"]:
        if d["format"] == "html":
            vocab_texts.append(html_to_text((ROOT / d["path"]).read_text(encoding="utf-8")))
    vocab = build_vocab(vocab_texts)

    all_pages: list[DocumentPage] = []
    log: dict[str, Any] = {"vocab_size": len(vocab), "documents": {}}
    for d in manifest["documents"]:
        path = ROOT / d["path"]
        if not path.exists():
            raise FileNotFoundError(f"Thiếu file nguồn {path}. Chạy: python scripts/fetch_corpus.py")
        if d["format"] == "pdf":
            pages, plog = load_pdf(path, d, vocab)
        elif d["format"] == "html":
            pages, plog = load_html(path, d)
        else:
            raise ValueError(f"Định dạng không hỗ trợ: {d['format']}")
        all_pages.extend(pages)
        summary = {
            "format": d["format"],
            "units": len(pages),
            "content_units": sum(1 for p in pages if p.metadata["is_content"]),
            "excluded_units": [e["location"] for e in plog if not e["is_content"]],
            "errors": [e for e in plog if "error" in e],
        }
        if d["format"] == "pdf":
            summary["lines_joined"] = sum(e["lines_joined"] for e in plog)
            summary["syllable_repairs"] = sum(e["syllable_repairs"] for e in plog)
        else:
            summary.update(plog[0].get("html_normalize_stats", {}))
        log["documents"][d["document_id"]] = {**summary, "details": plog}
    log["total_units"] = len(all_pages)
    log["total_content_units"] = sum(1 for p in all_pages if p.metadata["is_content"])
    return all_pages, log
