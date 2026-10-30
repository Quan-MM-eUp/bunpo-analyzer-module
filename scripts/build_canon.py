"""Tim mau trung trong kho va chon "mau chuan" cho moi nhom (buoc 3.2).

    python scripts/build_canon.py            # ghi src/bunpo_analyzer/tables/grammar_canon.json + docs/mau_trung.md

Hai id la mot mau khi bo luat bat chung DUNG cung vi tri tren >= 90% cau vi du
cua ca hai id (it nhat 5 cau) - tuc la luat khong phan biet duoc. Bo qua cap
co chu thich nghia khac nhau trong ten (のです（khẳng định） / のです（giải thích）).

Mau chuan = muc co du lieu day du nhat (explain, comparison, common_mistakes, notes,
vi du); bang nhau thi cap thap hon, roi id nho hon. Kho giu nguyen; module chi
dua mau chuan cho LLM va hien mau chuan tren the.
"""

from __future__ import annotations

import collections
import itertools
import json
import re
import sys
from pathlib import Path

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.data import get_kho
from bunpo_analyzer.core.input_check import check_input
from bunpo_analyzer.core.matcher import get_matcher
from bunpo_analyzer.core.tokenizer import tokenize
from bunpo_analyzer.evaluation import example_sentences

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "bunpo_analyzer" / "tables" / "grammar_canon.json"
DOC = ROOT / "docs" / "mau_trung.md"
MIN_CO, MIN_SHARE = 5, 0.9
_QUAL = re.compile(r"[（(［\[]([^）)］\]]*)[）)］\]]")
LV = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}


def qualifiers(name: str) -> set[str]:
    return {q.strip() for q in _QUAL.findall(name) if re.search(r"[a-zà-ỹ]", q.lower())}


def richness(g) -> int:
    r = g.raw
    return sum(bool((r.get(k) or "").strip()) for k in ("explain", "comparison", "common_mistakes", "notes")) * 1000 \
        + min(len(r.get("examples") or ""), 999)


def main() -> int:
    kho = get_kho(get_settings().data_dir)
    m = get_matcher()
    sents = {s for g in kho.grammars.values() for s in example_sentences(g.raw.get("examples"))
             if check_input(s).error is None}
    cnt: collections.Counter = collections.Counter()
    pair: collections.Counter = collections.Counter()
    for s in sents:
        pos: dict = collections.defaultdict(set)
        for x in m.match(tokenize(s)):
            pos[(x.core_start, x.core_end)].add(x.grammar_id)
        for i in set().union(*pos.values()) if pos else ():
            cnt[i] += 1
        for ids in pos.values():
            for a, b in itertools.combinations(sorted(ids), 2):
                pair[(a, b)] += 1
    par: dict[int, int] = {}

    def find(x: int) -> int:
        while par.setdefault(x, x) != x:
            x = par[x]
        return x

    skipped = []
    for (a, b), c in sorted(pair.items()):
        if c < MIN_CO or c < MIN_SHARE * cnt[a] or c < MIN_SHARE * cnt[b]:
            continue
        qa, qb = qualifiers(kho.grammar(a).name), qualifiers(kho.grammar(b).name)
        if qa and qb and qa != qb:
            skipped.append((a, b))
            continue
        par[find(a)] = find(b)
    groups: dict[int, set[int]] = {}
    for x in list(par):
        groups.setdefault(find(x), set()).add(x)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        gs = [kho.grammar(i) for i in members]
        canon = max(gs, key=lambda g: (richness(g), -LV.get(g.level or "", 9), -g.id)).id
        out.append({"canon": canon, "members": sorted(members),
                    "names": {str(i): f"{kho.grammar(i).level} {kho.grammar(i).name}" for i in sorted(members)}})
    out.sort(key=lambda g: g["canon"])
    data = {"version": 1, "kho_version": kho.core_version,
            "note": "Sinh tu dong boi scripts/build_canon.py. Sua tay duoc: doi canon, bo id khoi nhom.",
            "groups": out}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = ["# Mẫu trùng trong kho và mẫu chuẩn", "",
             f"Sinh bởi `scripts/build_canon.py`: {len(out)} nhóm, {sum(len(g['members']) for g in out)} id. "
             "Hai id được coi là một mẫu khi bộ luật bắt chung đúng cùng vị trí trên ≥ 90% câu ví dụ của cả hai. "
             "Mẫu chuẩn (**đậm**) là mục có dữ liệu đầy đủ nhất. Kho giữ nguyên; module chỉ đưa mẫu chuẩn cho LLM và hiện mẫu chuẩn trên thẻ.",
             "", "Muốn sửa: đổi `canon` hoặc bỏ id khỏi nhóm trong `src/bunpo_analyzer/tables/grammar_canon.json`.", "",
             "| Mẫu chuẩn | Các id gộp vào |", "|---|---|"]
    for g in out:
        others = ", ".join(f"#{i} {g['names'][str(i)]}" for i in g["members"] if i != g["canon"])
        lines.append(f"| **#{g['canon']} {g['names'][str(g['canon'])]}** | {others} |")
    if skipped:
        lines += ["", "Không gộp (tên ghi nghĩa khác nhau, để LLM tự chọn):", ""]
        lines += [f"- #{a} {kho.grammar(a).name} / #{b} {kho.grammar(b).name}" for a, b in skipped]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(out)} nhom -> {OUT.relative_to(ROOT)}, {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
