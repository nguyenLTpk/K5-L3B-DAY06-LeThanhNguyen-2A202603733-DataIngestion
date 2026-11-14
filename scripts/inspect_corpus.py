# -*- coding: utf-8 -*-
"""Đọc corpus, ghi ingest log, đối chiếu chéo PDF với bản HTML tham chiếu, xuất text đã chuẩn hóa.

Chạy:  python scripts/inspect_corpus.py [--write-manifest]
Đầu ra: results/ingest_log.json, results/normalized_units.jsonl (+ cập nhật data/manifest.json["units"]).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion import html_to_text, load_corpus, normalize_text  # noqa: E402


def key(text: str) -> str:
    t = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", t).strip()


N = 6


def ngrams(words: list[str]) -> list[tuple[str, ...]]:
    return [tuple(words[i:i + N]) for i in range(len(words) - N + 1)]


def cross_check(pages, manifest) -> dict:
    """Tỷ lệ 6-gram từ của PDF (sau chuẩn hóa) xuất hiện trong bản HTML tham chiếu của cùng văn bản."""
    ref_path = ROOT / manifest["normalization_reference"][0]["path"]
    ref_text, _ = normalize_text(html_to_text(ref_path.read_text(encoding="utf-8")))
    ref_set = set(ngrams(key(ref_text).split()))
    out = {"reference": manifest["normalization_reference"][0]["path"], "method": f"{N}-gram từ (chữ thường, bỏ dấu câu)", "pages": {}}
    tot = hit = 0
    for p in pages:
        if p.document_id != "tt08-2021" or not p.metadata["is_content"]:
            continue
        grams = ngrams(key(p.text).split())
        m = sum(1 for g in grams if g in ref_set)
        misses = sorted({" ".join(g) for g in grams if g not in ref_set})
        out["pages"][p.location] = {"ngrams": len(grams), "matched": m, "match_rate": round(m / len(grams), 4) if grams else None,
                                    "unmatched_sample": misses[:4]}
        tot += len(grams)
        hit += m
    out["overall_match_rate"] = round(hit / tot, 4) if tot else None
    out["note"] = "6-gram không khớp chủ yếu do lỗi tách chữ còn sót (cả hai mảnh đều là âm tiết hợp lệ, ví dụ 'khó a', hoặc chữ số '7 0%') và chỗ nối giữa hai trang."
    return out


def main() -> int:
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages, log = load_corpus(manifest_path)
    log["cross_check_tt08_pdf_vs_html"] = cross_check(pages, manifest)

    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    (results / "ingest_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(results / "normalized_units.jsonl", "w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps({"document_id": p.document_id, "location": p.location, "page": p.page,
                                "is_content": p.metadata["is_content"], "chars": len(p.text), "text": p.text},
                               ensure_ascii=False) + "\n")

    print(f"vocab_size={log['vocab_size']} total_units={log['total_units']} content_units={log['total_content_units']}")
    for doc_id, d in log["documents"].items():
        print(f"  {doc_id}: units={d['units']} content={d['content_units']}")
        for e in d["details"]:
            extra = ""
            if "syllable_repairs" in e:
                extra = f" printed={e['printed_page']} joined={e['lines_joined']} repairs={e['syllable_repairs']} oov {e['oov_rate_before_repair']}->{e['oov_rate_after_repair']}"
            print(f"    {e['location']:>4} chars={e['normalized_chars']:>5} content={e['is_content']}{extra} {e.get('warning', '')}")
    print("cross-check PDF vs HTML:", log["cross_check_tt08_pdf_vs_html"]["overall_match_rate"])

    if "--write-manifest" in sys.argv:
        manifest["units"] = [
            {"document_id": p.document_id, "location": p.location, "page": p.page,
             "printed_page": p.metadata.get("printed_page"), "chars": len(p.text), "is_content": p.metadata["is_content"]}
            for p in pages
        ]
        manifest["total_units"] = log["total_units"]
        manifest["total_content_units"] = log["total_content_units"]
        manifest["content_units_by_document"] = {k: v["content_units"] for k, v in log["documents"].items()}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print("manifest updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
