# -*- coding: utf-8 -*-
"""Tổng hợp nhãn thủ công + metric tự động thành results/audit/audit_summary.json và in bảng Markdown.

Kiểm tra chunk_id trong nhãn coherence còn khớp với phiếu hiện tại (phát hiện nhãn cũ khi chunking thay đổi).
Chạy sau `python -m src.run`:  python scripts/summarize_audits.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results" / "audit"


def load(name):
    return json.loads((AUDIT / name).read_text(encoding="utf-8"))


def main() -> int:
    coh, grd, meta = load("coherence_labels.json"), load("grounding_labels.json"), load("metadata_labels.json")
    sheet = {r["position_id"]: r for r in load("coherence_sheet.json")}
    summary = json.loads((ROOT / "results" / "benchmark_summary.json").read_text(encoding="utf-8"))
    traces = {s: json.loads((ROOT / "results" / f"traces_strategy_{s}.json").read_text(encoding="utf-8")) for s in "ABC"}

    stale = [f"{l['position_id']}:{s}" for l in coh["labels"] for s in "AB"
             if sheet[l["position_id"]][f"strategy_{s}"]["chunk_id"] != l[s]["chunk_id"]]
    if stale:
        print("NHÃN COHERENCE KHÔNG KHỚP PHIẾU HIỆN TẠI:", stale)
        return 1

    out = {}
    for s in "ABC":
        src = "B" if s == "C" else s
        cs = [l[src]["score"] for l in coh["labels"]]
        gs = [l[s]["score"] for l in grd["labels"]]
        gc = Counter(gs)
        fq = [t for t in traces[s] if t["question_filter"]]
        out[s] = {
            "coherence_mean": round(sum(cs) / len(cs), 2), "coherence_n": len(cs), "coherence_dist": dict(Counter(cs)),
            "metadata_correct": f"{meta['result'][s]['complete_and_correct']}/{meta['result'][s]['total']}",
            "filter_compliance_test": summary["strategies"][s]["test"]["top3_in_filter_scope"],
            "filter_compliance_all": f"{sum(1 for t in fq if t['top3_in_filter_scope'])}/{len(fq)}",
            "grounding_counts": {k: gc.get(k, 0) for k in (0, 1, 2)}, "grounding_mean": round(sum(gs) / len(gs), 2),
            "filter_applied": s == "C",
        }
    out["note"] = "Coherence của C = B (dùng chung chunk). Tuân thủ filter = mọi chunk top-3 thuộc đúng phạm vi regulation của câu có filter; với A/B (không lọc) đây là mức tự nhiên rơi vào đúng phạm vi."
    (AUDIT / "audit_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("| Strategy | Coherence /2 (n) | Metadata đủ & đúng | Filter tuân thủ test (tất cả) | Grounding 0/1/2 | Grounding TB /2 |")
    print("|---|---|---|---|---|---|")
    for s in "ABC":
        o = out[s]
        g = o["grounding_counts"]
        print(f"| {s} | {o['coherence_mean']} ({o['coherence_n']}) | {o['metadata_correct']} | {o['filter_compliance_test']} ({o['filter_compliance_all']}) | {g[0]}/{g[1]}/{g[2]} | {o['grounding_mean']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
