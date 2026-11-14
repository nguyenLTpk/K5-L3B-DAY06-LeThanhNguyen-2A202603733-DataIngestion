# -*- coding: utf-8 -*-
"""Embedding thật, chạy local: intfloat/multilingual-e5-small (ONNX, 384 chiều, đa ngữ có tiếng Việt).

- Tokenizer: HuggingFace `tokenizers` (tokenizer.json của model), cắt tối đa 512 token.
- Pooling: mean pooling theo attention mask (theo 1_Pooling/config.json của model), sau đó chuẩn hóa L2.
- Quy ước E5: document thêm tiền tố "passage: ", query thêm tiền tố "query: ".
- Không có fallback: thiếu file model hoặc sai checksum thì báo lỗi, không thay bằng vector ngẫu nhiên.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "multilingual-e5-small"
MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
ONNX_SHA256 = "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, question: str) -> list[float]: ...


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class E5OnnxEmbedder:
    def __init__(self, model_dir: Path = MODEL_DIR, max_length: int = 512, batch_size: int = 16, verify_checksum: bool = True) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        onnx_path = model_dir / "onnx_model.onnx"
        tok_path = model_dir / "onnx_tokenizer.json"
        if not onnx_path.exists() or not tok_path.exists():
            raise FileNotFoundError(f"Thiếu model tại {model_dir}. Chạy: python scripts/download_model.py")
        if verify_checksum and _sha256(onnx_path) != ONNX_SHA256:
            raise ValueError("Checksum ONNX không khớp với revision đã ghi — không dùng model khác thay thế")
        self.model_name = f"{MODEL_ID}@{MODEL_REVISION[:8]}"
        self.dimensions = 384
        self.max_length = max_length
        self.batch_size = batch_size
        self.tokenizer = Tokenizer.from_file(str(tok_path))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>"), pad_token="<pad>")
        so = ort.SessionOptions()
        so.intra_op_num_threads = 0
        self.session = ort.InferenceSession(str(onnx_path), sess_options=so, providers=["CPUExecutionProvider"])
        self.truncated_inputs = 0

    def _encode(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            enc = self.tokenizer.encode_batch(batch)
            self.truncated_inputs += sum(1 for e in enc if e.overflowing)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            hidden = self.session.run(["last_hidden_state"], feeds)[0]  # (b, seq, 384)
            m = mask[..., None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            out.append(pooled.astype(np.float32))
        return np.vstack(out) if out else np.zeros((0, self.dimensions), dtype=np.float32)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts]).tolist()

    def embed_query(self, question: str) -> list[float]:
        return self._encode([f"query: {question}"])[0].tolist()
