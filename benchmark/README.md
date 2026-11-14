# Benchmark — 20 câu hỏi (15 dev / 5 test)

File: [benchmark.json](benchmark.json) · Kiểm chứng: `python scripts/verify_benchmark.py` → [results/benchmark_verification.json](../results/benchmark_verification.json)

**Chốt lúc:** 2026-11-14, trước lần chạy truy xuất đầu tiên trên corpus này.
**sha256(benchmark.json) lúc chốt:** `77bb4ad253ae14da8081e931b7493bb9776b16e9da8767f2dc66b31ec06616e2`.
Sau mốc này không sửa câu hỏi, gold hay split. Nếu buộc phải sửa, ghi lại lý do ở mục "Thay đổi sau khi chốt" bên dưới.

## Cách xây dựng
- Câu hỏi viết từ text **đã chuẩn hóa** ([results/normalized_units.jsonl](../results/normalized_units.jsonl)). `evidence_quote` được chép nguyên văn từ đơn vị gold.
- Mỗi câu có: `id`, `split`, `type`, `question`, `expected_answer`, `gold_source_id`, `gold_page` (số trang PDF, hoặc số thứ tự đơn vị HTML), `gold_location` (`p7`, `u05`…), `gold_article`, `evidence_quote` và `filter` (nếu có). Câu có filter có thêm `context` (phạm vi người dùng chọn trước khi hỏi) và `confusable_with` (nội dung dễ nhầm ở văn bản khác).
- `verify_benchmark.py` kiểm tra: evidence có trong đúng trang/đơn vị gold, không xuất hiện nguyên văn ở vị trí khác, giá trị filter tồn tại trong metadata, filter không chứa gold source hay đáp án. Kết quả: 20/20 đạt, không có câu mơ hồ.
- Phân bố: TT 08/2021: 10 câu · TT 10/2016: 5 · TT 16/2015: 5. Loại câu: trực tiếp 5 · diễn đạt lại 4 · điều kiện/ngoại lệ 6 · metadata filter 5.
- Công cụ: các câu hỏi do Claude (trợ lý AI) soạn sau khi đọc toàn bộ text đã chuẩn hóa; học viên rà soát lại. Mọi câu đều có đáp án trong nguồn.

## Phân chia dev/test (chốt trước khi chạy)
- **Test (q16–q20)** chỉ lấy từ các Điều **không** được dùng ở dev: TT08 Điều 13 và 15, TT16 Điều 10 và 14, TT10 Điều 12. Script kiểm tra: `test_articles_overlapping_dev = []`.
- **Nguy cơ rò rỉ:** q17 (test, TT08 Điều 13) cùng trang p15 với q06 (dev, Điều 14). q18 (test, TT16 Điều 10) cùng đơn vị u05 với q09 (dev, Điều 9). Một chunk có thể chứa cả hai Điều, nên kết quả dev có thể "nhìn thấy" chunk của câu test. Không có tham số nào được tinh chỉnh dựa trên test.
- **Filter:** 5 câu (q05, q09, q12 thuộc dev; q18, q19 thuộc test), đều dùng trường `regulation`. Giá trị filter là **input giả định** do người dùng/giao diện cung cấp *trước khi truy xuất* (ví dụ người dùng đang ở mục "Quy chế đánh giá rèn luyện"). Mỗi câu filter nhắm vào khái niệm có ở ít nhất 2 văn bản ("xuất sắc", "giỏi", "khiển trách", "Chủ tịch Hội đồng"). Hạn chế: phạm vi `regulation` trùng với văn bản gold, nên filter là gợi ý mạnh. Đây đúng là tình huống chọn phạm vi trong ứng dụng thật, nhưng làm Hit của C trên câu filter dễ hơn.

## Cấu hình và tiêu chí chọn (chốt trước khi chạy)
| | Chunking | Truy xuất |
|---|---|---|
| A | Cửa sổ cố định 500 ký tự, overlap 50, trong từng đơn vị nguồn | cosine top-3, không lọc |
| B | Theo cấu trúc: cắt tại Điều/Chương (ranh giới cứng) và khoản/điểm (ranh giới mềm), gộp tối đa 800 ký tự | cosine top-3, không lọc |
| C | Giống hệt B (cùng chunk, cùng vector) | như B; **chỉ** câu có `filter` mới thêm `where regulation = …` |

Cùng corpus, cùng model embedding (multilingual-e5-small), cùng vector store (Chroma, cosine) và cùng định nghĩa metric cho cả ba cấu hình.

**Tiêu chí chọn chiến lược** (chỉ dùng dev, theo thứ tự ưu tiên):
1. Evidence Hit@3 trên dev cao hơn.
2. Nếu hòa: Hit@1 trên dev.
3. Nếu vẫn hòa: điểm coherence trung bình (mẫu 10 vị trí, chấm thủ công).
4. Nếu vẫn hòa: ít chunk hơn / thời gian ingest thấp hơn.

C chỉ áp dụng được khi có giá trị filter đáng tin từ ngữ cảnh. Test chạy một lần sau khi đã chốt lựa chọn, chỉ để báo cáo, không dùng để chỉnh.

## Thay đổi sau khi chốt
(chưa có)
