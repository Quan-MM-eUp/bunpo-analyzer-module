"""Mau chuan cho cac mau trung trong kho (buoc 3.2, docs/mau_trung.md).

Kho co nhieu muc cung mot mau (ようになる co 4 id). Module chi dua MAU CHUAN cho LLM
va hien mau chuan tren the: it ung vien hon, cung mot cau luon ra cung mot muc.
Bang sinh boi scripts/build_canon.py, sua tay duoc.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from bunpo_analyzer.core.matcher import Match

PATH = Path(__file__).resolve().parent.parent / "tables" / "grammar_canon.json"


@lru_cache(maxsize=1)
def _table() -> tuple[dict[int, int], dict[int, frozenset[int]]]:
    if not PATH.exists():
        return {}, {}
    data = json.loads(PATH.read_text(encoding="utf-8"))
    to_canon: dict[int, int] = {}
    members: dict[int, frozenset[int]] = {}
    for g in data.get("groups", []):
        ms = frozenset(int(x) for x in g["members"])
        for i in ms:
            to_canon[i] = int(g["canon"])
            members[i] = ms
    return to_canon, members


def canon_id(gid: int) -> int:
    return _table()[0].get(int(gid), int(gid))


def group_of(gid: int) -> frozenset[int]:
    return _table()[1].get(int(gid), frozenset({int(gid)}))


def canonicalize(matches: list[Match]) -> list[Match]:
    """Doi id sang mau chuan, bo trung (cung mau chuan, cung vi tri)."""
    out: list[Match] = []
    seen: set[tuple[int, int, int]] = set()
    for m in matches:
        c = canon_id(m.grammar_id)
        key = (c, m.core_start, m.core_end)
        if key in seen:
            continue
        seen.add(key)
        out.append(m if c == m.grammar_id else Match(c, m.start, m.end, m.core_start, m.core_end, m.tokens, m.rule_name))
    return out
