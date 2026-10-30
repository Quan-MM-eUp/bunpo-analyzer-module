"""Du lieu phu cho bang ngu phap (buoc 4.1, muc 11.7 file ke hoach).

    python scripts/build_grammar_meta.py   # ghi src/bunpo_analyzer/tables/grammar_meta.json + docs/grammar_meta_review.md

- confusable_ids: doi ten trong truong `confusable` (ngan bang ｜) sang id, so ten da bo
  khoang trang. Mau trung da gom (grammar_canon.json) thi tro ve mau chuan; bo chinh no.
- short_label: nhan ngan tren the. Kho chua co truong nay nen sinh tu dong:
  * ten mau (`grammar`) bo khoang trang giua chu Nhat: ～た　ことが　ある -> ～たことがある
  * ten co chu Viet NGOAI ngoac (Trợ từ と, Tính từ → Trạng từ...) ma `pattern` chi gom
    chu Nhat / ky hieu va ngan -> dung pattern (と, Aい→Aく / Na→Naに)
  * con lai giu ten (co chu Viet trong ngoac de phan biet nghia: ～から（lý do）).
  lang = "neutral" neu nhan khong co chu Viet (dung chung moi ngon ngu), "vi" neu co
  (ngon ngu khac lay ten da dich trong grammar_text.<lang>.json).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.canon import canon_id
from bunpo_analyzer.core.data import get_kho

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "bunpo_analyzer" / "tables" / "grammar_meta.json"
DOC = ROOT / "docs" / "grammar_meta_review.md"
MAX_PATTERN = 24

_JP = "ぁ-ゖァ-ヺー㐀-䶿一-鿿々～〜"
_J = f"{_JP}（）()・／/⇔→"
# Bo khoang trang giua chu Nhat voi chu Nhat / ky hieu N, V, A (N1に N2を V -> N1にN2をV);
# giu khoang trang canh chu Viet (V thể ý chí と思っています giu nguyen).
_SPACE_JP = re.compile(f"(?<=[{_J}])[ \u3000]+(?=[{_J}A-Z])|(?<=[A-Z0-9])[ \u3000]+(?=[{_J}])")
_VI = re.compile(r"[à-ỹđ]|[a-z]{3,}", re.I)
_KANA = re.compile(r"[ぁ-ゖァ-ヺ]")
_PAREN = re.compile(r"[（(［\[][^）)］\]]*[）)］\]]")


def tidy(s: str) -> str:
    return re.sub(r"\s+", " ", _SPACE_JP.sub("", (s or "").strip()))


def has_vi(s: str) -> bool:
    return bool(_VI.search(s))


def short_label(name: str, pattern: str) -> tuple[str, str]:
    p = tidy(pattern)
    outside = _PAREN.sub("", name)
    if not has_vi(outside):
        n = tidy(name)
    elif p and not has_vi(p) and len(p) <= MAX_PATTERN and (_KANA.search(p) or "→" in p):
        n = p
    else:
        n = re.sub(r"\s+", " ", name.strip())  # ten tieng Viet: giu nguyen
    return n, ("vi" if has_vi(n) else "neutral")


def norm(s: str) -> str:
    return re.sub(r"[\s　]", "", s or "")


def main() -> int:
    kho = get_kho(get_settings().data_dir)
    by_name: dict[str, list[int]] = {}
    for g in kho.grammars.values():
        by_name.setdefault(norm(g.name), []).append(g.id)
    meta: dict[str, dict] = {}
    unmatched: list[tuple[int, str]] = []
    changed: list[tuple[int, str, str]] = []
    for g in sorted(kho.grammars.values(), key=lambda g: g.id):
        label, lang = short_label(g.name, g.pattern)
        if label != g.name:
            changed.append((g.id, g.name, label))
        ids: list[int] = []
        for nm in re.split(r"[｜|]", g.raw.get("confusable") or ""):
            nm = nm.strip()
            if not nm:
                continue
            hit = by_name.get(norm(nm), [])
            if len(hit) != 1:
                unmatched.append((g.id, nm))
                continue
            c = canon_id(hit[0])
            if c != canon_id(g.id) and c not in ids:
                ids.append(c)
        meta[str(g.id)] = {"short_label": label, "label_lang": lang, "confusable_ids": ids}
    data = {"version": 1, "kho_version": kho.core_version,
            "note": "Sinh tu dong boi scripts/build_grammar_meta.py (buoc 4.1). Sua tay short_label duoc.",
            "grammar": meta}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_conf = sum(bool(m["confusable_ids"]) for m in meta.values())
    lines = ["# Nhãn ngắn và \"Dễ nhầm với\" (bước 4.1)", "",
             f"Sinh bởi `scripts/build_grammar_meta.py`. {len(meta)} mẫu; {n_conf} mẫu có \"Dễ nhầm với\"; "
             f"{len(unmatched)} tên không tìm được id. Nhãn khác tên gốc: {len(changed)} mẫu (bảng dưới). "
             f"Nhãn còn chữ Việt: {sum(m['label_lang'] == 'vi' for m in meta.values())} mẫu (ngôn ngữ khác dùng tên đã dịch).",
             "", "Muốn sửa: đổi `short_label` trong `src/bunpo_analyzer/tables/grammar_meta.json`.", "",
             "| id | Tên gốc | Nhãn ngắn |", "|---|---|---|"]
    lines += [f"| {i} | {a} | {b} |" for i, a, b in changed]
    if unmatched:
        lines += ["", "Tên trong `confusable` không tìm được id:", ""]
        lines += [f"- #{i}: {nm}" for i, nm in unmatched]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(meta)} mau, {n_conf} co confusable, {len(unmatched)} ten khong khop, {len(changed)} nhan doi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
