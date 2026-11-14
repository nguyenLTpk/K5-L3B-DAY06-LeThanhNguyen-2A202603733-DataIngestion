"""Shared data contracts; keep traceability from chunk back to source."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentPage:
    """Một đơn vị nguồn: 1 trang PDF vật lý, hoặc 1 đơn vị HTML (>= 1.500 ký tự)."""

    document_id: str
    source: str
    page: int  # số trang PDF vật lý, hoặc số thứ tự đơn vị HTML (u01 -> 1)
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> str:
        return self.metadata.get("location", f"p{self.page}")


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source: str
    page: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
