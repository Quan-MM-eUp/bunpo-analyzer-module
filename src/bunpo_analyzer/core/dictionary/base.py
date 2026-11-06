"""Kieu du lieu chung cho tu dien ngoai (Mazii...)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class Sense:
    mean: str
    kinds: tuple[str, ...] = ()  # tu loai kieu JMdict: n, vs, v5r, adj-i, adv...
    readings: tuple[str, ...] = ()  # cach doc ap dung (rong = moi cach doc)


@dataclass(frozen=True)
class DictEntry:
    id: str
    word: str
    readings: tuple[str, ...] = ()  # hiragana / katakana
    level: Optional[str] = None  # N5..N1
    han: Optional[str] = None  # am Han Viet (tu dien javi)
    short_mean: Optional[str] = None
    senses: tuple[Sense, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: dict[str, Any]) -> DictEntry:
        return DictEntry(
            id=d["id"], word=d["word"], readings=tuple(d.get("readings") or ()), level=d.get("level"),
            han=d.get("han"), short_mean=d.get("short_mean"),
            senses=tuple(Sense(s["mean"], tuple(s.get("kinds") or ()), tuple(s.get("readings") or ()))
                         for s in d.get("senses") or ()),
        )


class Dictionary(Protocol):
    """Tra nhieu tu cung luc. Tra ve {query: [DictEntry...]}; query loi / qua gio thi KHONG co trong dict."""

    async def search_many(self, queries: list[str], lang: str) -> dict[str, list[DictEntry]]: ...
