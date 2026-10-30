"""Cham chat luong (buoc 3.1, muc 8 file ke hoach). Dung cho scripts/eval.py va scripts/score_run.py.

Hai bo thu:
- golden: bo cau kiem thu (tests/golden/golden_set.json). Cau "full" co dap an cau truc
  (dong, nhom); cau "pattern" chi co mau bat buoc; cau loi / nghi sai / dau vao sai co
  trang thai mong doi.
- kho: cau vi du trong grammar_lib, da biet chac thuoc mau nao. Do 2 chi so: bo luat
  co dua mau dung vao ung vien khong, va LLM co chon dung mau khong.

Mau trung nhau duoc tinh la dung: cung nhom vi tri ung vien (vd 6 id cua ようになる),
hoac cung ten mau trong kho.
"""

from __future__ import annotations

import random
import re
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from bunpo_analyzer.core.input_check import check_input, normalize
from bunpo_analyzer.core.matcher import Match
from bunpo_analyzer.core.prompt import candidate_groups

PUNCT = re.compile(r"[、。？！?!\s　]")
# Tro tu co ban va です: prompt dan LLM bo qua khi chi la danh dau cach (muc 9, chinh sach bo cau thu).
from bunpo_analyzer.core.validator import BACKGROUND_IDS, BASIC_PARTICLE_IDS  # noqa: E402

BASIC_IDS = BASIC_PARTICLE_IDS | BACKGROUND_IDS

_ALT_SPLIT = re.compile(r"[/／・]")
_KANA_ANY = re.compile(r"[ぁ-ゖ]")
_JP = re.compile(r"[぀-ヿ一-鿿]")
_LATIN = re.compile(r"[a-zA-Zà-ỹĐđ]{3,}")


# ---------------- tien ich ----------------
def leaves(nodes):
    for n in nodes:
        if "group" in n:
            yield from leaves(n["children"])
        else:
            yield n


def walk(nodes):
    for n in nodes:
        yield n
        if "group" in n:
            yield from walk(n["children"])


def flat(ids):
    for x in ids:
        yield from (x if isinstance(x, list) else [x])


def equivalents(matches: list[Match], kho=None) -> dict[int, set[int]]:
    """id -> cac id coi la mot mau (cung nhom vi tri ung vien, hoac cung ten trong kho)."""
    same: dict[int, set[int]] = {}
    for _, ms in candidate_groups(matches):
        ids = {m.grammar_id for m in ms}
        for i in ids:
            same.setdefault(i, set()).update(ids)
    from bunpo_analyzer.core.canon import _table

    for i, ms in _table()[1].items():  # mau trung da gom (docs/mau_trung.md)
        same.setdefault(i, {i}).update(ms)
    if kho is not None:
        by_name: dict[str, set[int]] = {}
        for g in kho.grammars.values():
            by_name.setdefault(PUNCT.sub("", g.name).strip("～〜"), set()).add(g.id)
            # cung mot cach viet trong pattern: ～ないといけない (#59) va ～なくてはいけない/～ないといけない (#367)
            for alt in _ALT_SPLIT.split(g.pattern or ""):
                alt = PUNCT.sub("", alt).strip("～〜")
                if len(alt) >= 3 and _KANA_ANY.search(alt):
                    by_name.setdefault("p:" + alt, set()).add(g.id)
        for ids in by_name.values():
            if len(ids) > 1:
                for i in ids:
                    same.setdefault(i, {i}).update(ids)
    return same


def _eq(same: dict[int, set[int]], ids: Iterable[int]) -> set[int]:
    out: set[int] = set()
    for a in ids:
        out |= same.get(a, {a})
    return out


# ---------------- cham cau truc (cau "full") ----------------
def score_structure(text: str, surfaces: list[str], nodes: list[dict], gold: dict,
                    matches: list[Match], kho=None) -> dict:
    """nodes: dang dict cua LLMNode hoac Node (vi tri theo token)."""
    def txt(span):
        return PUNCT.sub("", "".join(surfaces[span[0]:span[1]])) if span else ""

    rows = [n for n in nodes if n["type"] == "row" and not n.get("hidden")]
    got_rows = {(n["role"] if not n.get("main") else "MAIN", txt(n["span"])) for n in rows}
    exp = gold["expect"]["structure"]
    exp_rows = {(n["role"] if not n.get("main") else "MAIN", PUNCT.sub("", n["text"]))
                for n in leaves(exp) if not n.get("hidden")}
    by_parent: dict[Any, list[dict]] = {}
    for n in nodes:
        by_parent.setdefault(n.get("parent"), []).append(n)

    def gtext(gid):
        s = ""
        for c in by_parent.get(gid, []):
            s += gtext(c["id"]) if c["type"] == "group" else (txt(c["span"]) if not c.get("hidden") else "")
        return s

    got_groups = {(n["kind"], gtext(n["id"])) for n in nodes if n["type"] == "group"}
    exp_groups = {(n["group"], PUNCT.sub("", n["text"])) for n in walk(exp) if "group" in n}
    covered = sorted(i for n in rows for i in range(*n["span"]) if n["span"])
    need = [i for i, s in enumerate(surfaces) if not PUNCT.fullmatch(s)]
    g = score_grammar({x for n in nodes for x in n.get("grammar", [])}, gold, matches, kho)
    return {
        "rows": (len(got_rows & exp_rows), len(exp_rows), len(got_rows)),
        "groups": (len(got_groups & exp_groups), len(exp_groups), len(got_groups)),
        **g,
        "coverage_ok": covered == need,
        "missing_rows": sorted(exp_rows - got_rows), "wrong_rows": sorted(got_rows - exp_rows),
        "missing_groups": sorted(exp_groups - got_groups), "wrong_groups": sorted(got_groups - exp_groups),
    }


def score_grammar(got_ids: set[int], gold: dict, matches: list[Match], kho=None) -> dict:
    same = equivalents(matches, kho)
    must = gold["expect"].get("grammar_must") or []
    hit = [bool(got_ids & _eq(same, m if isinstance(m, list) else [m])) for m in must]
    allowed = _eq(same, set(flat(must)) | set(flat(gold["expect"].get("grammar_ok") or [])))
    return {"must": (sum(hit), len(hit)), "extra": sorted(got_ids - allowed - BASIC_IDS),
            "missed": [m for m, h in zip(must, hit) if not h]}


# ---------------- cham trang thai (moi cau golden) ----------------
def check_status(gold: dict, result: dict) -> tuple[bool, str]:
    """So loi / auto_fix / input_check / cau sua voi dap an. Tra (dung?, ghi chu)."""
    e = gold["expect"]
    want_err = (e.get("error") or {}).get("code")
    got_err = (result.get("error") or {}).get("code")
    if want_err == "invalid_input":
        ok = got_err == "invalid_input" and (result.get("error") or {}).get("reason") == e["error"].get("reason")
        return ok, f"can invalid_input/{e['error'].get('reason')}, ra {got_err}/{(result.get('error') or {}).get('reason')}"
    notes = []
    ok = True
    want_fix = e.get("auto_fix")
    got_fix = (result.get("auto_fix") or {}).get("fixed")
    if want_fix != got_fix:
        ok = False
        notes.append(f"auto_fix can {want_fix} ra {got_fix}")
    if got_err in ("structure_failed", "llm_unavailable"):
        return False, f"loi {got_err}"
    want_ic = e.get("input_check")
    want_ic = want_ic if isinstance(want_ic, list) else [want_ic]
    ic = result.get("input_check") or {}
    if ic.get("status", "ok") not in want_ic:
        ok = False
        notes.append(f"input_check can {'/'.join(want_ic)} ra {ic.get('status', 'ok')}")
    if e.get("correction") and ic.get("status") == "error":
        if ic.get("correction") != e["correction"] or ic.get("correction_at") is None:
            ok = False
            notes.append(f"cau sua can {e['correction']} ra {ic.get('correction')}")
    if want_err != got_err:
        ok = False
        notes.append(f"error can {want_err} ra {got_err}")
    return ok, "; ".join(notes)


# ---------------- cau vi du trong kho ----------------
_ITEM = re.compile(r"^\s*(\d+[\.\)]|[①-⑳➀-➓❶-❿])")


def example_items(text: Optional[str]) -> list[list[str]]:
    """Cac vi du danh so (1., 2., ①...) cua mot mau; moi vi du la danh sach cau tieng Nhat.
    Vi du hoi thoai (A:/B:) co nhieu cau; mau chi nam o mot trong so do."""
    items: list[list[str]] = []
    for line in str(text or "").split("\n"):
        if _ITEM.match(line) or not items:
            items.append([])
        line = re.sub(r"^(\s*(\d+[\.\)]|[①-⑳➀-➓❶-❿]|[A-ZＡ-Ｚ][:：]|→)\s*)+", "", line.strip())
        line = re.sub(r"^[A-ZＡ-Ｚ][:：「]?", "", line)
        for part in re.split(r"(?<=[。！？])", line):
            part = part.strip(" 「」")
            if len(part) >= 3 and _JP.search(part) and not _LATIN.search(part):
                items[-1].append(normalize(part))
    return [it for it in items if it]


_BLOCK = re.compile(r"\n\s*─{3,}\s*\n")


def example_blocks(text: Optional[str]) -> list[list[list[str]]]:
    """321/1621 muc trong kho gop nhieu muc cu, ngan bang dong ──────. Khoi dau la nghia chinh
    cua mau; cac khoi sau co the la nghia / mau khac (#159 なる gop ca Naで, Naじゃない)."""
    return [example_items(b) for b in _BLOCK.split(str(text or ""))]


def example_sentences(text: Optional[str]) -> list[str]:
    return [s for it in example_items(text) for s in it]


@dataclass(frozen=True)
class KhoExample:
    grammar_id: int
    level: str
    text: str


def single_examples(g, max_chars: int = 100) -> list[str]:
    """Vi du 1 cau hop le trong khoi chinh: chac chan mau nam trong cau do (dung de cham)."""
    blocks = example_blocks(g.raw.get("examples"))
    return [it[0] for it in (blocks[0] if blocks else [])
            if len(it) == 1 and check_input(it[0], max_chars).error is None and not _fragment(it[0])
            and not _NOTE.search(it[0])]


# Loi thoai cat do (妻「…), ghi chu trong ngoac (父（怒って）), dau ＊ ＝ ／: khong phai cau sach de cham
_NOTE = re.compile(r"[「」『』（）()＊*＝=／/]")


def _fragment(text: str) -> bool:
    """Cum danh tu, khong phai cau (きのう買った本): bo khi cham vi LLM phai dung cau co vi ngu."""
    from bunpo_analyzer.core.tokenizer import tokenize

    toks = [t for t in tokenize(text) if t.pos != "punct"]
    return bool(toks) and toks[-1].pos == "noun" and not text.rstrip().endswith(("。", "？", "?", "！", "!"))


def kho_examples(kho, levels: Iterable[str], per_level: int, seed: int = 1, max_chars: int = 100) -> list[KhoExample]:
    """Moi cap lay toi da `per_level` mau (ngau nhien, co dinh theo seed), moi mau 1 cau vi du (vi du 1 cau)."""
    rng = random.Random(seed)
    out: list[KhoExample] = []
    for lv in levels:
        pool = []
        for g in sorted(kho.grammars.values(), key=lambda g: g.id):
            if g.level != lv:
                continue
            sents = single_examples(g, max_chars)
            if sents:
                pool.append(KhoExample(g.id, lv, rng.choice(sents)))
        rng.shuffle(pool)
        out += pool[:per_level]
    return out


def kho_hit(gid: int, got_ids: Iterable[int], matches: list[Match], kho=None) -> bool:
    return bool(set(got_ids) & _eq(equivalents(matches, kho), [gid]))


# ---------------- tong hop ----------------
def pct(a: float, b: float) -> str:
    return f"{a / b:.0%}" if b else "-"


def latency_stats(ms: list[int]) -> dict[str, int]:
    if not ms:
        return {"avg": 0, "p50": 0, "p95": 0, "max": 0}
    s = sorted(ms)
    return {"avg": int(statistics.mean(s)), "p50": s[len(s) // 2],
            "p95": s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))], "max": s[-1]}
