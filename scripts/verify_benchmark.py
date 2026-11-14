# -*- coding: utf-8 -*-
"""Kiểm chứng benchmark TRƯỚC khi chạy thí nghiệm.

- evidence_quote tồn tại nguyên văn (sau chuẩn hóa) trong đúng document/trang gold;
- liệt kê mọi vị trí khác cũng chứa evidence (phát hiện câu mơ hồ);
- đủ >= 20 câu, >= 15 dev / >= 5 test, >= 3 câu filter trong đó >= 1 câu test;
- giá trị filter tồn tại trong metadata corpus; filter không chứa gold_source_id/đáp án.

Chạy: python scripts/verify_benchmark.py   -> results/benchmark_verification.json
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation import match_key  # noqa: E402
from src.ingestion import load_corpus  # noqa: E402


def main() -> int:
    bench_path = ROOT / "benchmark" / "benchmark.json"
    questions = json.loads(bench_path.read_text(encoding="utf-8"))
    pages, _ = load_corpus(ROOT / "data" / "manifest.json")
    by_loc = {(p.document_id, p.page): p for p in pages}
    regulations = {p.metadata["regulation"] for p in pages}

    rows, problems = [], []
    for q in questions:
        ev = match_key(q["evidence_quote"])
        gold = by_loc.get((q["gold_source_id"], int(q["gold_page"])))
        in_gold = bool(gold) and ev in match_key(gold.text)
        loc_ok = bool(gold) and gold.location == q.get("gold_location")
        also_in = [f"{p.document_id}:{p.location}" for p in pages
                   if ev in match_key(p.text) and not (p.document_id == q["gold_source_id"] and p.page == int(q["gold_page"]))]
        flt = q.get("filter") or {}
        flt_ok = all(k == "regulation" and v in regulations for k, v in flt.items())
        leak = any(str(v) in (q["gold_source_id"], q.get("expected_answer", "")) for v in flt.values())
        if not in_gold:
            problems.append(f"{q['id']}: evidence không có trong {q['gold_source_id']} trang {q['gold_page']}")
        if not loc_ok:
            problems.append(f"{q['id']}: gold_location không khớp")
        if also_in:
            problems.append(f"{q['id']}: evidence cũng xuất hiện ở {also_in}")
        if flt and not flt_ok:
            problems.append(f"{q['id']}: giá trị filter không tồn tại trong metadata")
        if leak:
            problems.append(f"{q['id']}: filter chứa gold source/đáp án")
        rows.append({"id": q["id"], "split": q["split"], "type": q["type"], "gold": f"{q['gold_source_id']}:{q.get('gold_location')}",
                     "evidence_chars": len(q["evidence_quote"]), "evidence_found_in_gold": in_gold,
                     "evidence_also_in": also_in, "filter": flt or None, "filter_values_exist": flt_ok if flt else None})

    split = Counter(q["split"] for q in questions)
    n_filter = sum(1 for q in questions if q.get("filter"))
    n_filter_test = sum(1 for q in questions if q.get("filter") and q["split"] == "test")
    if len(questions) < 20 or split["dev"] < 15 or split["test"] < 5:
        problems.append(f"Số câu/phân chia chưa đạt: {dict(split)}")
    if n_filter < 3 or n_filter_test < 1:
        problems.append(f"Câu filter chưa đạt: {n_filter} (test {n_filter_test})")

    dev_articles = {(q["gold_source_id"], q["gold_article"]) for q in questions if q["split"] == "dev"}
    overlap = [q["id"] for q in questions if q["split"] == "test" and (q["gold_source_id"], q["gold_article"]) in dev_articles]

    report = {
        "benchmark_sha256": hashlib.sha256(bench_path.read_bytes()).hexdigest(),
        "n_questions": len(questions), "split": dict(split),
        "types": dict(Counter(q["type"] for q in questions)),
        "by_document": dict(Counter(q["gold_source_id"] for q in questions)),
        "filter_questions": n_filter, "filter_questions_test": n_filter_test,
        "test_articles_overlapping_dev": overlap,
        "all_evidence_verified": all(r["evidence_found_in_gold"] for r in rows),
        "problems": problems, "questions": rows,
    }
    out = ROOT / "results" / "benchmark_verification.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "questions"}, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
