# -*- coding: utf-8 -*-
"""Tải corpus gốc (3 văn bản quy phạm pháp luật) và lưu snapshot vào data/raw/.

- TT 08/2021/TT-BGDĐT (Quy chế đào tạo trình độ đại học): PDF, lưu nguyên file.
- TT 10/2016/TT-BGDĐT (Quy chế công tác sinh viên) và TT 16/2015/TT-BGDĐT
  (Quy chế đánh giá kết quả rèn luyện): trang HTML trên caselaw.vn; chỉ giữ khối
  nội dung văn bản (div#divContentDoc), bỏ menu/quảng cáo của trang.
- Bản HTML của TT 08/2021 trên caselaw.vn được lưu vào data/reference/ để làm
  từ điển âm tiết khi sửa lỗi tách chữ của PDF và để đối chiếu chéo nội dung.

Chạy: python scripts/fetch_corpus.py
Script in ra sha256 của từng file; giá trị đã dùng được ghi trong data/manifest.json.
"""
import hashlib
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REF = ROOT / "data" / "reference"
UA = {"User-Agent": "Mozilla/5.0 (Day06 data-ingestion lab)"}

SOURCES = [
    {
        "out": RAW / "tt08_2021_quy_che_dao_tao.pdf",
        "url": "https://spnttw.edu.vn/wp-content/uploads/2021/05/thong-tu-08-1-da-gop.pdf",
        "kind": "pdf",
    },
    {
        "out": RAW / "tt10_2016_quy_che_cong_tac_sinh_vien.html",
        "url": "https://caselaw.vn/van-ban-phap-luat/262795-thong-tu-10-2016-tt-bgddt-ve-quy-che-cong-tac-sinh-vien-doi-voi-chuong-trinh-dao-tao-dai-hoc-he-chinh-quy-do-bo-truong-bo-giao-duc-va-dao-tao-ban-hanh",
        "kind": "html",
    },
    {
        "out": RAW / "tt16_2015_quy_che_danh_gia_ren_luyen.html",
        "url": "https://caselaw.vn/van-ban-phap-luat/263580-thong-tu-16-2015-tt-bgddt-ve-quy-che-danh-gia-ket-qua-ren-luyen-cua-nguoi-hoc-duoc-dao-tao-trinh-do-dai-hoc-he-chinh-quy-do-bo-truong-bo-giao-duc-va-dao-tao-ban-hanh",
        "kind": "html",
    },
    {
        "out": REF / "tt08_2021_caselaw.html",
        "url": "https://caselaw.vn/van-ban-phap-luat/365862-thong-tu-so-08-2021-tt-bgddt-ngay-18-03-2021-cua-bo-truong-bo-giao-duc-va-dao-tao-ve-quy-che-dao-tao-trinh-do-dai-hoc",
        "kind": "html",
    },
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_content_div(html: str) -> str:
    """Lấy khối <div id="divContentDoc"> (đếm cặp thẻ div để tìm điểm đóng)."""
    start = html.find('id="divContentDoc"')
    if start < 0:
        raise ValueError("Không tìm thấy div#divContentDoc — cấu trúc trang đã đổi")
    start = html.rfind("<div", 0, start)
    depth, pos = 0, start
    tag = re.compile(r"<(/?)div\b[^>]*>", re.I)
    for m in tag.finditer(html, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            pos = m.end()
            break
    else:
        raise ValueError("div#divContentDoc không đóng")
    return html[start:pos]


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    REF.mkdir(parents=True, exist_ok=True)
    print(f"accessed_at: {date.today().isoformat()}")
    for src in SOURCES:
        req = urllib.request.Request(src["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
        if src["kind"] == "pdf":
            if not raw.startswith(b"%PDF"):
                raise ValueError(f"{src['url']} không trả về PDF")
            out_bytes = raw
        else:
            fragment = extract_content_div(raw.decode("utf-8"))
            out_bytes = ("<!-- source: " + src["url"] + " -->\n" + fragment).encode("utf-8")
        src["out"].write_bytes(out_bytes)
        print(f"{src['out'].relative_to(ROOT)}  download_sha256={sha256(raw)}  saved_sha256={sha256(out_bytes)}  bytes={len(out_bytes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
