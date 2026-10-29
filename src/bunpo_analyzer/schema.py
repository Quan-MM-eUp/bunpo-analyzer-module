"""Khuon AnalysisResult tra cho chatbot / app (muc 11.5 file ke hoach).

Day la hop dong voi team app: chi THEM truong, khong doi truong cu.
Doi khuon thi tang SCHEMA_VERSION.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.3"  # 1.3: them Token.pos_sub

Pos = Literal["noun", "verb", "adj", "adv", "prt", "aux", "punct"]
# Phan loai chi tiet hien khi bam vao tu: dong tu nhom 1/2/3, tinh tu い/な.
PosSub = Literal["v1", "v2", "v3", "adj_i", "adj_na"]
Role = Literal[
    "subject", "topic", "object", "complement", "predicate",
    "adv_time", "adv_place", "adv_manner", "adv_reason",
]
GroupKind = Literal["rel", "sub", "quote", "nominal"]
MeaningSource = Literal["word_lib", "particle_table", "llm"]
CheckStatus = Literal["ok", "suspect", "error"]
ErrorCode = Literal["invalid_input", "grammar_error", "structure_failed", "llm_unavailable"]

# [bat dau, ket thuc) - khoang nua mo.
Span = tuple[int, int]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Token(_Base):
    i: int = Field(ge=0)
    surface: str
    base: Optional[str] = None
    reading: Optional[str] = None
    pos: Pos
    pos_sub: Optional[PosSub] = None
    # Moi doan: [chu, cach doc | null]; chi kanji moi co cach doc.
    furigana: Optional[list[tuple[str, Optional[str]]]] = None
    meaning: Optional[str] = None
    meaning_source: Optional[MeaningSource] = None


class Node(_Base):
    id: str
    type: Literal["row", "group"]
    parent: Optional[str] = None
    span: Optional[Span] = None
    grammar: list[int] = Field(default_factory=list)
    # row
    role: Optional[Role] = None
    jp: Optional[str] = None
    gloss: Optional[str] = None
    main: bool = False
    hidden: bool = False
    # group
    kind: Optional[GroupKind] = None
    head: Optional[int] = None
    head_text: Optional[str] = None

    @model_validator(mode="after")
    def _check_type(self) -> "Node":
        if self.type == "row":
            if self.role is None:
                raise ValueError(f"row {self.id}: thieu role")
            if self.span is None and not self.hidden:
                raise ValueError(f"row {self.id}: chi chu ngu an moi duoc thieu span")
        else:
            if self.kind is None:
                raise ValueError(f"group {self.id}: thieu kind")
        if self.span is not None and self.span[0] >= self.span[1]:
            raise ValueError(f"{self.id}: span {self.span} khong hop le")
        return self


class GrammarItem(_Base):
    id: int
    short_label: Optional[str] = None
    level: Optional[str] = None
    # Nguyen van meaning_vi (hoac ban dich theo lang) trong kho - muc 12.10.
    meaning: Optional[str] = None
    # Cho leader quyet (12.10): huong de xuat bo o ban 1.
    note: Optional[str] = None


class InputCheck(_Base):
    status: CheckStatus = "ok"
    at: Optional[Span] = None
    reason: Optional[str] = None
    explain: Optional[str] = None
    correction: Optional[str] = None
    # Vi tri ky tu phan da sua trong correction; backend tinh bang diff.
    correction_at: Optional[Span] = None


class AutoFix(_Base):
    original: str
    fixed: str


class ErrorInfo(_Base):
    code: ErrorCode
    reason: Optional[str] = None


class AnalysisResult(_Base):
    schema_version: str = SCHEMA_VERSION
    id: str
    lang: str
    text: str
    translation: Optional[str] = None
    tokens: list[Token] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    grammar: list[GrammarItem] = Field(default_factory=list)
    input_check: InputCheck = Field(default_factory=InputCheck)
    auto_fix: Optional[AutoFix] = None
    error: Optional[ErrorInfo] = None

    @model_validator(mode="after")
    def _check_refs(self) -> "AnalysisResult":
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("nodes co id trung nhau")
        for n in self.nodes:
            if n.parent is not None and n.parent not in ids:
                raise ValueError(f"{n.id}: parent {n.parent} khong ton tai")
        if self.error is not None and self.error.code == "grammar_error":
            if self.nodes or self.grammar or self.translation:
                raise ValueError("grammar_error thi khong co nodes, grammar, translation")
        return self
