# Báo cáo cá nhân — Day 6

**Họ và tên:** Lê Thành Nguyên · **MSSV:** 2A202603733 · **Lớp:** K5-L3B
**Chủ đề:** Truy xuất quy chế dành cho sinh viên đại học chính quy (3 văn bản quy phạm pháp luật của Bộ GD&ĐT)
**Lệnh tái lập:** xem [README.md](../../README.md#2-cài-đặt-và-chạy) · Lần chạy chính thức: 2026-11-14 04:08 UTC ([run_metadata.json](../../results/run_metadata.json))

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - Corpus gồm 3 văn bản thật ([manifest](../../data/manifest.json)):
    - **TT 08/2021/TT-BGDĐT** — Quy chế đào tạo trình độ đại học. PDF 22 trang, nguồn spnttw.edu.vn.
    - **TT 10/2016/TT-BGDĐT** — Quy chế công tác sinh viên. HTML, nguồn caselaw.vn.
    - **TT 16/2015/TT-BGDĐT** — Quy chế đánh giá kết quả rèn luyện. HTML, nguồn caselaw.vn.
  - Quyền sử dụng: văn bản quy phạm pháp luật không thuộc đối tượng bảo hộ quyền tác giả (khoản 2 Điều 15 Luật Sở hữu trí tuệ). Với nguồn HTML, repo chỉ lưu khối nội dung văn bản, không lưu giao diện trang. Mỗi file có sha256 để đối chiếu; tải lại bằng `scripts/fetch_corpus.py`.
  - **51 đơn vị nội dung** (yêu cầu ≥ 30):
    - 20 trang PDF (p3–p22, mỗi trang ≥ 300 ký tự nội dung quy chế). Trang p1–p2 là ảnh scan, không có lớp text, không OCR nên bị loại và ghi log.
    - 22 + 9 đơn vị HTML, mỗi đơn vị ≥ 1.500 ký tự đã chuẩn hóa, chia theo thứ tự tại ranh giới dòng.
  - Danh sách đơn vị và số ký tự từng đơn vị nằm trong `manifest.units`.
  - Ngày hiệu lực ghi theo nội dung văn bản. Tình trạng hiệu lực hiện tại của TT 10/2016 và TT 16/2015 **chưa được kiểm chứng**; corpus là snapshot ngày 2026-11-14, không dùng để tư vấn quy định hiện hành.
- **Chuẩn hóa, lỗi và giới hạn** ([ingest_log.json](../../results/ingest_log.json)):
  - Các bước chung: chuẩn hóa Unicode NFC; bỏ NBSP/zero-width; gộp khoảng trắng; bỏ khoảng trắng trước dấu câu.
  - PDF:
    - Bỏ số trang in ở đầu trang và giữ lại làm `printed_page`.
    - Nối 386 dòng bị ngắt cứng; giữ xuống dòng tại Chương/Điều/khoản/điểm.
    - **Sửa 95 lỗi tách âm tiết** ("đà o tạo" → "đào tạo", "Điề u" → "Điều"). Cách làm: chỉ gộp khi một mảnh không có trong từ điển âm tiết *và* kết quả gộp có trong từ điển. Từ điển (881 âm tiết) lấy từ bản HTML sạch của cùng văn bản ([data/reference](../../data/reference/), không được index).
    - Tỷ lệ OOV mỗi trang giảm từ tối đa 3,3% xuống tối đa 0,45%.
  - HTML:
    - Cắt 139 ký tự rác giao diện ("Nội dung VB / Văn bản gốc / … đăng nhập") ở cuối mỗi file.
    - Sửa 50 chữ bị caselaw.vn viết hoa giữa câu ("bảo đảm Điều kiện" → "điều kiện").
  - **Đối chiếu chéo:** 99,42% 6-gram từ của PDF sau chuẩn hóa xuất hiện trong bản HTML của cùng văn bản. Lỗi còn sót gồm: các trường hợp cả hai mảnh đều là âm tiết hợp lệ ("khó a", 2 lần), chữ số bị tách ("7 0%"), "n ơi", "đươ c".
  - Giới hạn khác:
    - Phụ lục dạng bảng của TT 10 bị làm phẳng, mất cột "số lần vi phạm", nên không đặt câu hỏi vào phần này.
    - Một lỗi tách đoạn sai: dòng bắt đầu bằng "10." (thang điểm 10) bị hiểu là khoản mới.
    - Chunk không vượt ranh giới trang/đơn vị, nên Điều kéo dài qua hai trang bị tách; có 3 chunk B < 120 ký tự.
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - Embedding: `intfloat/multilingual-e5-small`, revision `614241f6`, bản ONNX chính thức (sha256 `ca456c06…`), 384 chiều, chạy local bằng onnxruntime 1.32.0 trên CPU.
  - Xử lý: tokenizers 0.23.3, tối đa 512 token (không input nào bị cắt; lớn nhất 240 token). Mean pooling rồi chuẩn hóa L2; tiền tố `passage: ` cho document và `query: ` cho câu hỏi.
  - Không có fallback: thiếu model hoặc sai checksum thì dừng.
  - Vector store: ChromaDB 1.5.9 `PersistentClient` tại `results/chroma_db`, `hnsw:space = cosine`. HNSW là tìm kiếm **xấp xỉ**, nhưng top-3 HNSW khớp top-3 exact (numpy) ở **20/20** câu cho cả A/B/C.
  - Lệnh chạy: `python -m src.run`. Thời gian: embed + lưu A 10,8 s, B 13,1 s; 20 truy vấn ≈ 0,3 s mỗi cấu hình; toàn pipeline 31 s.
  - **Chi phí $0** (không gọi API trả phí; tải model ~490 MB một lần).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Bắt buộc: `document_id`, `source` (đường dẫn file), `page` (số trang PDF hoặc số đơn vị HTML), `location` (`p16`, `u05`).
  - Trường lọc `regulation` (chuỗi, 3 giá trị): lấy từ tiêu đề văn bản và ghi trong manifest, không suy đoán. Lý do chọn: 3 quy chế dùng chung khái niệm ("xuất sắc", "khiển trách", "Chủ tịch Hội đồng"); người dùng thường biết mình đang tra quy chế nào.
  - Trường truy vết thêm: `doc_code`, `issued_year`, `chapter`, `article`, `articles_covered`, `start_char`/`end_char`, `printed_page`. Các trường Chương/Điều lấy từ tiêu đề trong text.

## Cấu hình và benchmark

- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  - **A:** cửa sổ cố định 500 ký tự, overlap 50, trong từng đơn vị nguồn → 222 chunk.
  - **B:** theo cấu trúc. Ranh giới cứng tại Chương/Điều, ranh giới mềm tại khoản/điểm; gộp tối đa 800 ký tự; dòng > 800 ký tự tách theo câu; tiêu đề Chương gắn vào Điều kế tiếp → 178 chunk.
  - **C:** dùng **chung index và vector với B**. Khác biệt duy nhất: câu có `filter` được truy vấn kèm `where regulation = …`; câu không có filter chạy y hệt B.
  - A–B chỉ thay chunking; B–C chỉ thay bước lọc. Cùng corpus, model, store, metric và câu hỏi cho cả ba.
- **≥ 20 câu: phân chia, câu metadata filter và cách kiểm chứng evidence** ([benchmark/README.md](../../benchmark/README.md)):
  - 20 câu: 15 dev, 5 test. Theo văn bản: TT08 10 câu, TT10 5, TT16 5. Theo loại: trực tiếp 5, diễn đạt lại 4, điều kiện/ngoại lệ 6, metadata filter 5.
  - Test chỉ lấy từ các Điều không dùng ở dev. Rò rỉ theo trang được ghi rõ: q17 chung trang với q06, q18 chung đơn vị với q09.
  - 5 câu filter: q05, q09, q12 (dev); q18, q19 (test). Giá trị filter là input giả định do người dùng chọn trước khi truy xuất.
  - `scripts/verify_benchmark.py` xác nhận: 20/20 evidence có nguyên văn trong đúng trang gold, không xuất hiện ở vị trí khác, giá trị filter tồn tại trong metadata, filter không chứa đáp án.
  - Benchmark được chốt (sha256 `77bb4ad2…`) trước lần truy xuất đầu tiên.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:** (1) Evidence Hit@3 trên dev → (2) Hit@1 trên dev → (3) coherence → (4) ít chunk/ingest nhanh hơn. C chỉ áp dụng khi có giá trị filter đáng tin.

## Kết quả

Định nghĩa hit: chunk đúng `document_id`, đúng trang/đơn vị gold **và** chứa đủ evidence (chuỗi con sau khi chuẩn hóa chữ thường/bỏ dấu câu). Không chấm khớp một phần.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A (fixed 500/50) | dev | 9/15 | 9/15 | 222 | embed+lưu 10,8 s; 20 truy vấn 0,32 s | $0 |
| A | test | 2/5 | 3/5 | 222 | (cùng lần chạy) | $0 |
| B (structure ≤ 800) | dev | 10/15 | 13/15 | 178 | embed+lưu 13,1 s; 20 truy vấn 0,31 s | $0 |
| B | test | 4/5 | **5/5** | 178 | (cùng lần chạy) | $0 |
| C (B + filter) | dev | 10/15 | **14/15** | 178 (chung index B) | không ingest thêm; 20 truy vấn 0,32 s | $0 |
| C | test | 4/5 | **5/5** | 178 | (cùng lần chạy) | $0 |

Nếu chỉ yêu cầu đúng trang (không cần chứa đủ evidence), dev: A 14/15, B 13/15, C 14/15; test: 5/5 cả ba. Khoảng cách A–B nằm ở chỗ chunk có giữ trọn evidence hay không, không phải ở chỗ tìm đúng trang.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,9 (10) — 0:1, 1:9 | 15/15 | test 1/2 (cả bộ 3/5), không lọc | 1 / 1 / 3 — **1,4** |
| B | 1,9 (10) — 1:1, 2:9 | 15/15 | test 1/2 (cả bộ 1/5), không lọc | 0 / 0 / 5 — **2,0** |
| C | 1,9 (10) — = B | 15/15 | **test 2/2 (cả bộ 5/5)** | 0 / 0 / 5 — **2,0** |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace top-3 đầy đủ (text, score, metadata, cờ hit, độ phủ evidence): [traces_strategy_A](../../results/traces_strategy_A.json), [B](../../results/traces_strategy_B.json), [C](../../results/traces_strategy_C.json). Tổng hợp: [benchmark_summary.json](../../results/benchmark_summary.json). Nhật ký: [experiment_log.csv](../../artifacts/experiment_log.csv).
- Phiếu chấm do pipeline sinh: [results/audit/*_sheet.json](../../results/audit/).
- Nhãn kèm lý do từng mục: [coherence_labels](../../results/audit/coherence_labels.json), [metadata_labels](../../results/audit/metadata_labels.json), [grounding_labels](../../results/audit/grounding_labels.json). Tổng hợp: [audit_summary.json](../../results/audit/audit_summary.json), sinh bởi `scripts/summarize_audits.py`.
- Mẫu coherence: 10 đơn vị nội dung cách đều nhau theo thứ tự corpus, vị trí = ký tự giữa đơn vị. Quy tắc này cố định trong `src/audit.py` trước khi chấm.
- Mẫu metadata và grounding: 5 câu test × top-3.
- Coherence của C bằng B vì dùng cùng chunk.
- Tuân thủ filter = toàn bộ top-3 nằm trong phạm vi `regulation` của câu. Với A/B (không lọc), con số này cho thấy mức tự nhiên rơi đúng phạm vi.
- Ngoài ra: nạp lại cùng phiên bản không nhân đôi (222/178 bản ghi, 0 embed lại; [reload_check.json](../../results/reload_check.json)). Mô phỏng tài liệu đổi: xóa 1 chunk cũ, embed lại 1 chunk sửa ([store_sync_test.json](../../results/store_sync_test.json)).

## Phân tích và kết luận

- **So sánh A–B và B–C; ví dụ sai có ID câu và nguồn:**
  - **A–B (chỉ thay chunking).** B hơn A 4 câu Evidence Hit@3 trên dev (13 so với 9) và 2 câu trên test (5 so với 3).
    - Lỗi chính của A là **cửa sổ cắt ngang evidence**. Ở q04, q11, q12, q15, q20, A vẫn trả về đúng trang nhưng không chunk nào chứa trọn câu.
    - Coherence của A chỉ 0,9/2: cả 10 mẫu A đều có đầu hoặc cuối bị cắt giữa từ. 9 mẫu được 1 điểm; pos02 = 0 vì mất câu dẫn "Quy chế của cơ sở đào tạo quy định:", khiến danh sách "Việc …" không còn nghĩa.
    - Ngược lại, A thắng Hit@1 ở q01, q02, q09: cửa sổ ngắn tập trung đúng câu hỏi hơn chunk B ~500–800 ký tự, nên B xếp chunk trang kề lên hạng 1 (q01: B hạng 1 là p8, gold p7 ở hạng 2).
    - Chi phí B tương đương A: ít chunk hơn (178 so với 222), tổng token ít hơn (24.137 so với 26.715), embed lâu hơn ~2 s.
  - **B–C (chỉ thêm filter).**
    - Filter cứu đúng 1 câu: **q09** (dev, gold tt16-2015:u05, Điều 9). Không lọc, B trả top-3 gồm tt08-2021:p10 (thang điểm chữ A–D), tt10-2016:u08 (danh hiệu sinh viên Xuất sắc) và tt16-2015:u06. Có `regulation = quy_che_danh_gia_ren_luyen`, chunk Điều 9 lên hạng 2.
    - Câu không có filter giữ nguyên kết quả. Tỷ lệ top-3 đúng phạm vi tăng từ 1/5 lên 5/5.
    - Ở q18 (test), B vẫn hit nhưng hạng 2 là tt10-2016:u15 (văn bản khác). C loại bỏ được nhiễu này.
  - **Ví dụ sai 1 — q20 (test), gold tt16-2015:u09, Điều 14.** Top-1 của A là `tt16-2015:u09:fix03`, mở đầu bằng "kỳ liên tiếp thì phải tạm ngừng học…". Điều kiện "Người học bị xếp loại rèn luyện yếu, kém trong hai học" nằm ở cửa sổ trước. Kết quả: đúng trang nhưng không hit, grounding = 1. B trả trọn khoản 5 nên đạt 2.
  - **Ví dụ sai 2 — q17 (test), gold tt08-2021:p15, Điều 13.** Hai chunk A hạng 1–2 đúng Điều 13, nhưng cửa sổ thứ hai dừng ở "3. Cơ sở đào tạo công khai q", nên câu "không vượt quá 50%" không có trong top-3 (grounding 0).
  - **Ví dụ sai 3 — q14 (dev), gold tt10-2016:u10, sai ở cả 3 cấu hình.** Câu hỏi diễn đạt lại ("đã bị khiển trách mà lại vi phạm tiếp") so với văn bản ("đã bị khiển trách mà tái phạm"). Top-3 của B/C là Điều 11 (chấm dứt hiệu lực kỷ luật khiển trách) và `tt10-2016:u09:st03`, chunk chỉ gồm tiêu đề và câu dẫn Điều 9. Tiêu đề và câu dẫn nằm cuối đơn vị HTML u09, còn các điểm a)–d) sang u10, nên chunk chứa "b) Cảnh cáo" mất câu dẫn và xếp thấp hơn. Đây là giới hạn của dense retrieval với câu diễn đạt lại, cộng với việc chia đơn vị HTML theo độ dài cắt ngang một Điều.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - Theo tiêu chí đã chốt, chọn **C** (dev Hit@3 14/15 > B 13/15 > A 9/15). Test chạy một lần sau khi chốt: C = B = 5/5 Hit@3, 4/5 Hit@1; A 3/5.
  - C chỉ có ích khi ứng dụng biết trước người dùng đang tra quy chế nào. Không có giá trị đó thì C chính là B.
  - Đánh đổi:
    - Chunk theo cấu trúc giữ trọn khoản/điểm (coherence 1,9, grounding 2,0) nhưng đôi khi mất Hit@1 vào chunk lân cận.
    - Filter theo `regulation` loại nhiễu khác văn bản, nhưng nếu người dùng chọn sai phạm vi thì sẽ loại luôn câu trả lời đúng. Ngoài ra `regulation` trùng 1-1 với văn bản gold, nên đây là gợi ý mạnh.
    - Chunk A với `article` duy nhất không đủ để trích dẫn ở 6/15 bản ghi kiểm tra (chunk trải 2–3 Điều); B là 0/15.
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Test chỉ 5 câu: mỗi câu = 20%, chênh 1 câu không có ý nghĩa thống kê. Dev 15 câu: mỗi câu ≈ 6,7%. Kết quả chỉ đúng cho corpus này.
  - Trên test, B và C bằng nhau; khác biệt B–C chỉ dựa vào 1 câu dev.
  - Nhãn coherence, metadata (phần thủ công) và grounding do **Claude (trợ lý AI) chấm** theo thang GUIDE, kèm lý do; học viên rà soát lại.
    - Không chấm mù: người chấm thấy kết quả Hit@3 tự động.
    - Mẫu coherence chỉ 10 vị trí.
    - Câu hỏi benchmark cũng do AI soạn từ text đã chuẩn hóa, nên có thể thiên về cách diễn đạt gần văn bản.
  - Thời gian đo trên một máy (CPU Intel, Windows 11), một lần chạy, chưa lặp lại; có biến động.
  - Văn bản có thể đã hết hiệu lực; corpus không bao gồm Công văn đính chính 2684/BGDĐT-GDĐH.
  - **Ghi chú quy trình (trung thực):**
    - Bản nháp trước của repo dùng một corpus tổng hợp do script tạo. Bản này đã bị loại bỏ hoàn toàn; corpus, benchmark và kết quả hiện tại được làm mới từ đầu.
    - Sau lần chạy đầu, khi chấm audit, đã phát hiện và sửa 2 lỗi metadata: (1) chunk mở đầu bằng tiêu đề Chương bị gán Điều của Chương trước; (2) `sync()` chỉ băm text nên không ghi lại metadata đã sửa.
    - Hit@1/Hit@3 trước và sau khi sửa giống hệt. Không có tham số chunking/truy xuất nào được chỉnh sau khi xem kết quả.
  - **Công cụ AI:** Claude (Anthropic) hỗ trợ viết code, soạn câu hỏi, chấm nhãn và viết báo cáo. Cách kiểm tra:
    - Script kiểm chứng evidence.
    - Đối chiếu chéo PDF với HTML.
    - So sánh HNSW với exact search.
    - Kiểm thử đồng bộ store.
    - Đọc lại toàn văn từng chunk được chấm.
- **Nếu làm lại hoặc mở rộng, cải tiến gì?**
  - Cho chunk B vượt ranh giới trang (giữ danh sách trang) và lặp câu dẫn/tiêu đề Điều vào đầu chunk con, để sửa lỗi kiểu q14 và pos07.
  - Thử hybrid BM25 + dense (RRF) trên dev cho câu chứa con số/thuật ngữ, và query expansion cho câu diễn đạt lại.
  - OCR 2 trang scan của Thông tư; tách bảng Phụ lục TT10 thành từng dòng có cột.
  - Tạo thêm tập test mới, lớn hơn (≥ 20 câu), do người khác viết, và chấm mù.
