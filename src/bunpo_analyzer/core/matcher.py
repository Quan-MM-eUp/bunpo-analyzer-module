"""Do mau ngu phap bang luat (buoc 1.5, muc 3.3 file ke hoach).

Luat dat trong `bunpo_analyzer/rules/*.json` (JSON thay YAML: khong them
thu vien PyYAML, chatbot dang co y tranh). Moi file:

    {"version": "0.1", "rules": [
      {"id": 613, "name": "～ようになる",
       "patterns": [[
         {"pos": ["verb", "aux"], "cform": ["終止形", "連体形"], "ctx": true},
         {"surface": "よう"}, {"surface": "に"}, {"base": "なる"}
       ]],
       "examples": ["上手に話せるようになった。"],
       "not_examples": ["そのように言った。"]}
    ]}

Moi phan tu cua pattern la dieu kien cho MOT token (tat ca dieu kien phai dung):
- surface, base, norm, reading, pos      : bang dung (chuoi hoac danh sach "mot trong")
- pos1, pos2, pos3, cform, ctype         : khop phan dau (cform "仮定形" khop "仮定形-一般")
- not: {...}                              : token KHONG duoc thoa dieu kien nay
- optional: true                          : token co the vang mat
- ctx: true                               : token ngu canh (vi du dong tu dung truoc),
                                            khong tinh vao phan "mau" (core span)
Hoac phan tu bo qua: {"gap": 3} = bo qua 0-3 token bat ky (khong vuot qua 。！？).
Hoac phan tu neo (khong chiem token): {"bos": true} dau cau, {"eos": true} cuoi cau
(phia sau chi con dau cau). Vi du: [{"bos": true}, {"surface": "でも"}].

Mau khong viet duoc luat theo token thi ghi vao "llm_only": [{"id", "name", "reason"}]
de LLM tu nhan dien; moi id chi xuat hien mot lan (luat hoac llm_only).

Luat duoc phep bat du (LLM loc lai sau); dieu can tranh la bo sot.
`examples` / `not_examples` duoc test tu dong (tests/test_matcher.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bunpo_analyzer.core.tokenizer import MorphToken

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
Str = Union[str, list[str]]
_SENT_END = {"。", "！", "？", "!", "?"}


class Cond(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    surface: Optional[Str] = None
    base: Optional[Str] = None
    norm: Optional[Str] = None
    reading: Optional[Str] = None
    pos: Optional[Str] = None
    pos1: Optional[Str] = None
    pos2: Optional[Str] = None
    pos3: Optional[Str] = None
    cform: Optional[Str] = None
    ctype: Optional[Str] = None
    not_: Optional["Cond"] = Field(default=None, alias="not")
    optional: bool = False
    ctx: bool = False
    gap: Optional[int] = Field(default=None, ge=1, le=10)
    bos: bool = False  # neo dau cau / dau ve sau 。！？ (khong chiem token)
    eos: bool = False  # neo cuoi cau: phia sau chi con dau cau (khong chiem token)

    @property
    def anchor(self) -> bool:
        return self.bos or self.eos

    @model_validator(mode="after")
    def _check(self) -> "Cond":
        tests = [self.surface, self.base, self.norm, self.reading, self.pos, self.pos1,
                 self.pos2, self.pos3, self.cform, self.ctype, self.not_]
        if self.anchor:
            if any(t is not None for t in tests) or self.optional or self.ctx or self.gap is not None or (self.bos and self.eos):
                raise ValueError("phan tu neo (bos/eos) khong kem dieu kien khac")
        elif self.gap is not None:
            if any(t is not None for t in tests) or self.optional or self.ctx:
                raise ValueError("phan tu gap khong kem dieu kien khac")
        elif all(t is None for t in tests):
            raise ValueError("dieu kien rong: dung {\"gap\": n} neu muon bo qua token")
        return self

    def matches(self, t: MorphToken) -> bool:
        def eq(v: Optional[Str], x: Optional[str]) -> bool:
            return v is None or (x in v if isinstance(v, list) else x == v)

        def pre(v: Optional[Str], x: Optional[str]) -> bool:
            if v is None:
                return True
            x = x or ""
            return any(x.startswith(s) for s in (v if isinstance(v, list) else [v]))

        pd = t.pos_detail
        ok = (
            eq(self.surface, t.surface) and eq(self.base, t.base) and eq(self.norm, t.norm)
            and eq(self.reading, t.reading) and eq(self.pos, t.pos)
            and pre(self.pos1, pd[0] if pd else None) and pre(self.pos2, pd[1] if len(pd) > 1 else None)
            and pre(self.pos3, pd[2] if len(pd) > 2 else None)
            and pre(self.cform, t.cform) and pre(self.ctype, t.ctype)
        )
        return ok and not (self.not_ is not None and self.not_.matches(t))

    def literals(self) -> set[str]:
        """Chuoi bat buoc phai co trong cau (de loc nhanh)."""
        if self.optional or self.gap is not None or self.anchor:
            return set()
        out = set()
        for v in (self.surface, self.base):
            if isinstance(v, str):
                out.add(v)
        return out


Cond.model_rebuild()


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str = ""
    patterns: list[list[Cond]] = Field(min_length=1)
    examples: list[str] = Field(default_factory=list)
    not_examples: list[str] = Field(default_factory=list)
    note: str = ""

    @field_validator("patterns")
    @classmethod
    def _non_empty(cls, ps: list[list[Cond]]) -> list[list[Cond]]:
        for p in ps:
            core = [c for c in p if c.gap is None and not c.anchor and not c.ctx and not c.optional]
            if not core:
                raise ValueError("pattern phai co it nhat 1 token thuoc mau (khong ctx, khong optional)")
            if p[0].gap is not None or p[-1].gap is not None:
                raise ValueError("gap khong dung o dau / cuoi pattern")
        return ps


class LlmOnly(BaseModel):
    """Mau khong viet duoc luat theo token (de LLM tu nhan dien)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str = ""
    reason: str


class RuleFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.1"
    note: str = ""
    rules: list[Rule] = Field(default_factory=list)
    llm_only: list[LlmOnly] = Field(default_factory=list)


@dataclass(frozen=True)
class Match:
    grammar_id: int
    start: int  # token dau (ca ngu canh)
    end: int  # token cuoi + 1
    core_start: int  # phan thuoc mau, khong tinh token ngu canh
    core_end: int
    tokens: tuple[int, ...]  # cac token da khop dieu kien (khong tinh gap)
    rule_name: str = ""

    def text(self, toks: list[MorphToken]) -> str:
        return "".join(t.surface for t in toks[self.core_start:self.core_end])


def _walk(p: list[Cond], k: int, i: int, toks: list[MorphToken], acc: list[tuple[int, bool]]) -> Iterator[list[tuple[int, bool]]]:
    """Quay lui: acc = [(chi so token, la ngu canh)]."""
    if k == len(p):
        yield acc
        return
    c = p[k]
    if c.bos:
        if i == 0 or toks[i - 1].surface in _SENT_END:
            yield from _walk(p, k + 1, i, toks, acc)
        return
    if c.eos:
        if all(t.pos == "punct" for t in toks[i:]):
            yield from _walk(p, k + 1, i, toks, acc)
        return
    if c.gap is not None:
        for skip in range(0, c.gap + 1):
            j = i + skip
            if j > len(toks) or any(t.surface in _SENT_END for t in toks[i:j]):
                break
            yield from _walk(p, k + 1, j, toks, acc)
        return
    if i < len(toks) and c.matches(toks[i]):
        yield from _walk(p, k + 1, i + 1, toks, acc + [(i, c.ctx)])
    if c.optional:
        yield from _walk(p, k + 1, i, toks, acc)


class GrammarMatcher:
    def __init__(self, rules: list[Rule], llm_only: Optional[list[LlmOnly]] = None) -> None:
        self.llm_only = llm_only or []
        seen: set[int] = {x.id for x in self.llm_only}
        for r in rules:
            if r.id in seen:
                raise ValueError(f"trung id luat: {r.id}")
            seen.add(r.id)
        self.rules = rules
        self._lits = [[set().union(*(c.literals() for c in p)) for p in r.patterns] for r in rules]

    @classmethod
    def from_dir(cls, path: Path | str = RULES_DIR) -> "GrammarMatcher":
        rules: list[Rule] = []
        llm_only: list[LlmOnly] = []
        for f in sorted(Path(path).glob("*.json")):
            try:
                rf = RuleFile.model_validate(json.loads(f.read_text(encoding="utf-8")))
            except Exception as e:  # bao ro file loi
                raise ValueError(f"{f.name}: {e}") from e
            rules += rf.rules
            llm_only += rf.llm_only
        return cls(rules, llm_only)

    def match(self, toks: list[MorphToken]) -> list[Match]:
        words = {t.surface for t in toks} | {t.base for t in toks}
        found: dict[tuple[int, int, int], Match] = {}
        for r, lits in zip(self.rules, self._lits):
            for p, lit in zip(r.patterns, lits):
                if not lit <= words:
                    continue
                for i in range(len(toks)):
                    for acc in _walk(p, 0, i, toks, []):
                        if not acc:
                            continue
                        idx = [a for a, _ in acc]
                        core = [a for a, ctx in acc if not ctx] or idx
                        m = Match(r.id, idx[0], idx[-1] + 1, core[0], core[-1] + 1, tuple(idx), r.name)
                        key = (r.id, m.core_start, m.core_end)
                        if key not in found or m.end - m.start > found[key].end - found[key].start:
                            found[key] = m
                        break  # moi vi tri bat dau lay ket qua dau tien cua pattern
        # Cung mau, phan mau long nhau: giu phan dai hon
        out = sorted(found.values(), key=lambda m: (m.core_start, -(m.core_end - m.core_start), m.grammar_id))
        kept: list[Match] = []
        for m in out:
            if any(k.grammar_id == m.grammar_id and k.core_start <= m.core_start and m.core_end <= k.core_end for k in kept):
                continue
            kept.append(m)
        return kept

    def candidate_ids(self, toks: list[MorphToken]) -> list[int]:
        return list(dict.fromkeys(m.grammar_id for m in self.match(toks)))


@lru_cache(maxsize=None)
def get_matcher() -> GrammarMatcher:
    return GrammarMatcher.from_dir(RULES_DIR)
