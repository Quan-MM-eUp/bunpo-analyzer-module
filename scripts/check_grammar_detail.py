"""Soat du lieu bang ngu phap sau khi lam sach (buoc 4.2).

    python scripts/check_grammar_detail.py   # ghi docs/grammar_detail_review.md

Liet ke cho team noi dung: mau khong co vi du, vi du thieu ban dich, mau chi co hoi thoai,
vi du bi lech ban dich (so dong Nhat / Viet khac nhau), bang so sanh khong doc duoc.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.grammar_detail import grammar_detail

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "grammar_detail_review.md"


def main() -> int:
    kho = get_kho(get_settings().data_dir)
    no_ex, no_vi, only_dialog, uneven, bad_cmp = [], [], [], [], []
    stats = {"examples": 0, "mistakes": 0, "comparison": 0, "confusable": 0, "notes": 0}
    for g in sorted(kho.grammars.values(), key=lambda g: g.id):
        d = grammar_detail(g.id, "vi", kho)
        tag = f"#{g.id} {d.short_label}"
        stats["examples"] += bool(d.examples)
        stats["mistakes"] += bool(d.mistakes)
        stats["comparison"] += bool(d.comparison)
        stats["confusable"] += bool(d.confusable)
        stats["notes"] += bool(d.notes)
        if not d.examples:
            no_ex.append(tag)
        if any(not e.vi for e in d.examples):
            no_vi.append(tag + ": " + next(e.jp for e in d.examples if not e.vi).replace("\n", " / "))
        if d.examples and all(e.dialog for e in d.examples):
            only_dialog.append(tag)
        for e in d.examples:
            if e.dialog and e.vi and e.jp.count("\n") != e.vi.count("\n"):
                uneven.append(tag + ": " + e.jp.replace("\n", " / "))
                break
        if (g.raw.get("comparison") or "").strip() and not d.comparison:
            bad_cmp.append(tag)
    n = len(kho.grammars)
    lines = ["# Soát dữ liệu bảng ngữ pháp (bước 4.2)", "",
             f"Sinh bởi `scripts/check_grammar_detail.py` trên {n} mẫu. Dữ liệu lấy thẳng từ kho, làm sạch lúc đọc "
             "(`core/grammar_detail.py`); sửa kho là hiện ngay.", "",
             "| Phần | Số mẫu có |", "|---|---|",
             *[f"| {k} | {v} |" for k, v in stats.items()], ""]
    for title, items in [("Không có ví dụ", no_ex), ("Ví dụ thiếu bản dịch (ví dụ đầu tiên thiếu)", no_vi),
                         ("Chỉ có ví dụ hội thoại A/B", only_dialog),
                         ("Hội thoại có số dòng Nhật / Việt khác nhau (có thể lệch bản dịch)", uneven),
                         ("Bảng so sánh không đọc được", bad_cmp)]:
        lines += [f"## {title} ({len(items)})", ""] + [f"- {x}" for x in items] + [""]
    DOC.write_text("\n".join(lines), encoding="utf-8")
    print(f"{n} mau; khong vi du {len(no_ex)}, thieu dich {len(no_vi)}, chi hoi thoai {len(only_dialog)}, "
          f"lech dong {len(uneven)}, bang loi {len(bad_cmp)} -> {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
