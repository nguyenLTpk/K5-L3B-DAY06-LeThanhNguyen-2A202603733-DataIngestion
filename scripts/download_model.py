# -*- coding: utf-8 -*-
"""Tải intfloat/multilingual-e5-small (bản ONNX, revision cố định) vào models/multilingual-e5-small/.

Chạy: python scripts/download_model.py   (~490 MB; thư mục models/ nằm trong .gitignore)
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.embeddings import MODEL_DIR, MODEL_ID, MODEL_REVISION, ONNX_SHA256  # noqa: E402

FILES = ["onnx/model.onnx", "onnx/tokenizer.json", "config.json", "1_Pooling/config.json"]


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        out = MODEL_DIR / f.replace("/", "_")
        if out.exists():
            print(f"skip {out.name} (đã có)")
            continue
        url = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{f}"
        print(f"download {url}")
        urllib.request.urlretrieve(url, out)
    h = hashlib.sha256((MODEL_DIR / "onnx_model.onnx").read_bytes()).hexdigest()
    print("onnx sha256:", h, "OK" if h == ONNX_SHA256 else "SAI CHECKSUM")
    return 0 if h == ONNX_SHA256 else 1


if __name__ == "__main__":
    sys.exit(main())
