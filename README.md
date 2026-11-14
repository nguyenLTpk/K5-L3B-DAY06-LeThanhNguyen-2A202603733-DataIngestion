# Day 06 · Data Ingestion Engineering — Lê Thành Nguyên (2A202603733, K5-L3B)

Pipeline biến 3 quy chế dành cho sinh viên đại học thành kho tri thức truy xuất được, rồi so sánh 3 chiến lược dữ liệu trên cùng benchmark 20 câu.

- **Corpus:** 3 văn bản quy phạm pháp luật thật của Bộ GD&ĐT, tổng **51 đơn vị nội dung**:
  - TT 08/2021 — Quy chế đào tạo: PDF, 20 trang nội dung.
  - TT 10/2016 — Quy chế công tác sinh viên: HTML, 22 đơn vị ≥ 1.500 ký tự.
  - TT 16/2015 — Quy chế đánh giá rèn luyện: HTML, 9 đơn vị.
- **Embedding:** `intfloat/multilingual-e5-small` (ONNX, local, 384 chiều).
- **Vector store:** ChromaDB 1.5.9 lưu trên đĩa, cosine, filter metadata.
- **Chi phí:** $0.

Báo cáo đầy đủ: [report/individual/2A202603733_LeThanhNguyen.md](report/individual/2A202603733_LeThanhNguyen.md)

## 1. Kết quả chính

| Strategy | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 | Chunks | Coherence /2 | Grounding /2 (test) | Filter tuân thủ |
|---|---|---|---|---|---|---|---|---|
| A — cửa sổ 500/50 | 9/15 | 9/15 | 2/5 | 3/5 | 222 | 0,9 | 1,4 | 3/5 (không lọc) |
| B — theo Điều/khoản ≤ 800 | 10/15 | 13/15 | 4/5 | 5/5 | 178 | 1,9 | 2,0 | 1/5 (không lọc) |
| **C — B + filter `regulation`** | 10/15 | **14/15** | 4/5 | 5/5 | 178 (chung index B) | 1,9 | 2,0 | **5/5** |

C được chọn theo tiêu chí chốt trước trên dev (Evidence Hit@3). Metadata đủ và đúng ở 15/15 bản ghi kiểm tra cho mỗi cấu hình. Test chỉ có 5 câu nên chỉ mang tính minh họa.

## 2. Cài đặt và chạy

Yêu cầu: Python 3.11+ và mạng cho lần tải đầu (model ~490 MB). Không cần API key hay Docker. Đã chạy trên Windows 11, CPU.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python scripts/download_model.py        # tải model ONNX vào models/ (revision cố định, kiểm tra sha256)
python scripts/fetch_corpus.py          # (tùy chọn) tải lại nguồn vào data/raw/ — repo đã kèm sẵn; so sha256 với manifest
python scripts/inspect_corpus.py --write-manifest   # đọc + chuẩn hóa, ghi ingest log, đối chiếu chéo PDF với HTML
python scripts/verify_benchmark.py      # kiểm chứng evidence/split/filter TRƯỚC khi chạy thí nghiệm
python -m src.run                       # pipeline A/B/C: chunk, embed, lưu Chroma, truy xuất, trace, metric, phiếu audit
python scripts/test_store_sync.py       # kiểm thử nạp lại + xử lý tài liệu thay đổi (trên Chroma tạm)
python scripts/summarize_audits.py      # tổng hợp nhãn thủ công + metric -> results/audit/audit_summary.json
```

Đặt `PYTHONIOENCODING=utf-8` nếu terminal Windows không hiển thị được tiếng Việt. `python -m src.run` mất khoảng 30 giây trên CPU. Lệnh này tạo lại `results/chroma_db/` (không commit) và **không** ghi đè các file nhãn `results/audit/*_labels.json`.

## 3. Cấu trúc repo

```text
STUDENT.md                     thông tin học viên
requirements.txt               phiên bản thư viện đã dùng
src/                           code pipeline
  ingestion.py                 đọc PDF/HTML, NFC, nối dòng, sửa tách âm tiết, chia đơn vị HTML, theo dõi Chương/Điều
  chunking.py                  A: fixed_size(500, 50) · B: by_structure(800)
  embeddings.py                E5 ONNX (mean pooling + L2, tiền tố query:/passage:)
  store.py                     Chroma PersistentClient, cosine, sync() idempotent, where-filter
  evaluation.py                Hit@1, Evidence Hit@3 (định nghĩa chặt), tuân thủ filter, trace
  audit.py                     quy tắc chọn mẫu + phiếu chấm coherence/metadata/grounding
  run.py                       điều phối pipeline, experiment log, run metadata
scripts/                       fetch_corpus, download_model, inspect_corpus, verify_benchmark, test_store_sync, summarize_audits
data/
  manifest.json                nguồn, quyền, sha256, quy tắc tính, danh sách 53 đơn vị (51 nội dung)
  raw/                         TT08 (PDF), TT10 + TT16 (khối nội dung HTML)
  reference/                   HTML TT08 — chỉ làm từ điển âm tiết và đối chiếu chéo, không index
benchmark/                     benchmark.json (20 câu: 15 dev / 5 test) + README (split, filter, tiêu chí chọn, sha256)
artifacts/experiment_log.csv   cấu hình, giả thuyết, kết quả A/B/C
results/                       ingest_log, normalized_units, benchmark_verification, traces_strategy_{A,B,C},
                               benchmark_summary, reload_check, store_sync_test, run_metadata, audit/
report/individual/2A202603733_LeThanhNguyen.md
starter/                       starter gốc của đề bài (pgvector, không dùng; giữ nguyên template)
```

## 4. Dữ liệu và quyền sử dụng

Cả 3 tài liệu là văn bản quy phạm pháp luật, không thuộc đối tượng bảo hộ quyền tác giả (khoản 2 Điều 15 Luật Sở hữu trí tuệ). Với 2 nguồn HTML (caselaw.vn), repo chỉ lưu khối nội dung văn bản. Nguồn, sha256, ngày truy cập, ghi chú hiệu lực và quy tắc tính trang nằm trong [data/manifest.json](data/manifest.json). Corpus là snapshot ngày 2026-11-14 dùng cho lab, không dùng để tư vấn quy định hiện hành. Repo không chứa secret, `.env` hay dữ liệu cá nhân.

## 5. Tài liệu đề bài

[GUIDE.md](GUIDE.md) · [BENCHMARK.md](BENCHMARK.md) · [RUBRIC.md](RUBRIC.md) · [RULES.md](RULES.md) · [SUBMISSION.md](SUBMISSION.md) · [CHECKPOINTS.md](CHECKPOINTS.md)
