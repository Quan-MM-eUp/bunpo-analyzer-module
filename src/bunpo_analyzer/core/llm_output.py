"""Khuon dau ra tho cua LLM (buoc 2.2, muc 3.4 file ke hoach).

Khac voi AnalysisResult (muc 11.5): day la thu LLM tra ve TRUOC khi code kiem
tra (2.3) va ghep (2.5). Danh sach node phang co `parent`. Tu prompt v3, span /
head / at do LLM tra theo so thu tu CUM (core/chunker.py); pipeline doi sang so
thu tu token truoc khi kiem tra va hien thi. Moi truong deu bat buoc (strict mode cua OpenAI), truong khong dung thi null.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from bunpo_analyzer.schema import GroupKind, Role


class _B(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMNode(_B):
    id: str = Field(description="r1, r2... cho dong; g1, g2... cho nhom")
    type: Literal["row", "group"]
    parent: Optional[str] = Field(description="id nhom chua node nay; null = ngoai cung")
    role: Optional[Role] = Field(description="chi cho row")
    kind: Optional[GroupKind] = Field(description="chi cho group")
    span: Optional[list[int]] = Field(description="row: [cum dau, cum cuoi + 1); null neu hidden. group: null")
    head: Optional[int] = Field(description="group rel: so thu tu cum chua danh tu duoc bo nghia; con lai null")
    hidden: bool = Field(description="true = chu ngu an, khong co trong cau")
    jp: Optional[str] = Field(description="chi cho dong an, vi du （私が）")
    gloss: Optional[str] = Field(description="nghia cua phan nay trong cau, bang ngon ngu dich")
    main: bool = Field(description="true cho dung 1 dong vi ngu chinh cua ca cau")
    grammar: list[int] = Field(description="id mau ngu phap (chi trong danh sach ung vien) gan vao node nay")


class LLMInputCheck(_B):
    status: Literal["ok", "suspect", "error"]
    at: Optional[list[int]] = Field(description="[cum dau, cum cuoi + 1) cua cho sai / nghi sai")
    reason: Optional[str] = Field(description="suspect: ly do ngan")
    explain: Optional[str] = Field(description="error: giai thich ngan vi sao sai")
    correction: Optional[str] = Field(description="error: ca cau da sua dung, giu nguyen y va thi")


class ReadingFix(_B):
    word: str = Field(description="tu chu Han (dung mat chu nhu trong cau)")
    reading: str = Field(description="cach doc hiragana dung trong ngu canh")


class WordMeaning(_B):
    word: str
    meaning: str


class LLMOutput(_B):
    input_check: LLMInputCheck
    translation: Optional[str] = Field(description="ban dich ca cau; null khi status = error")
    nodes: list[LLMNode] = Field(description="rong khi status = error")
    reading_fixes: list[ReadingFix] = Field(description="chi khi cach doc cho san sai trong ngu canh")
    word_meanings: list[WordMeaning] = Field(description="nghia cho cac tu duoc yeu cau (chua co trong kho)")
