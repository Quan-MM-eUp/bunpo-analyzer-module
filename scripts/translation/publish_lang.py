"""Dua ban dich kho ngu phap cua 1 ngon ngu vao module - 1 lenh cho moi ngon ngu.

    python scripts/translation/publish_lang.py en              # chay trong thu muc bunpo-analyzer
    python scripts/translation/publish_lang.py ko --ws ../translation --data ..

1. Gop out/<lang> (merge.py: lo passed / qa_low; bo muc lech voi nguon luc dong goi).
2. Bo muc ma kho tieng Viet da sua sau khi dong goi (so ma bam voi kho hien tai): mau do hien tieng Viet
   den khi dich bu (C7).
3. Nhan ngan: mau co nhan chu Viet (hoac chu Anh, voi ngon ngu khac tieng Anh) lay theo thu tu
   translation/labels/<lang>.json (dich tren Cowork) -> ten da dich. Con thieu: ghi
   translation/labels/<lang>.todo.json de dich (chua dich thi module dung nhan goc).
4. Ghi <data>/grammar/grammar_text.<lang>.json; bang tro tu particles/<lang>.json -> tables/ (export_particles).
5. In bao cao. Ma thoat 1 neu co loi (nhan dich sai khuon, bang tro tu loi); grammar_text van duoc ghi.

Chi doc translation/ (tru labels/<lang>.todo.json). Khoi dong lai tien trinh dung module de nap ban moi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import _norm
from common import LANGS, VI_ONLY, deruby, jp_runs, read_json, workspace, write_json
from export_batches import build_item
from export_particles import export_lang as export_particles
from merge import merge_lang

from bunpo_analyzer.config import get_settings
from bunpo_analyzer.core.canon import canon_id
from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.grammar_meta import _table as meta_table

KEEP_META = ("src_hash", "qa", "score", "date")


def label_errors(src: str, label, where: str) -> list[str]:
    if not isinstance(label, str) or not label.strip():
        return [f"{where}: rong"]
    errs = []
    if VI_ONLY.search(label):
        errs.append(f"{where}: con chu tieng Viet")
    miss = [r for r in jp_runs(deruby(src)) if _norm(r) not in _norm(label)]
    if miss:
        errs.append(f"{where}: mat chu Nhat {miss[:3]}")
    return errs


def build_labels(kho: Kho, out: dict, labels: dict, lang: str) -> tuple[dict, list[str], int]:
    """Gan short_label vao out. Tra (todo, loi, so nhan tu labels/<lang>.json)."""
    todo, errs, used = {}, [], 0
    for gid, m in sorted(meta_table().items()):
        if m.get("label_lang", "neutral") in ("neutral", lang) or canon_id(gid) != gid or kho.grammar(gid) is None:
            continue  # nhan dung duoc cho lang / mau trung lay nhan mau chuan
        rec = out.get(str(gid)) or {}
        lab = labels.get(str(gid))
        if lab is not None:
            e = label_errors(m["short_label"], lab, f"labels/{lang}.json[{gid}]")
            if not e:
                out.setdefault(str(gid), {})["short_label"] = lab.strip()
                used += 1
                continue
            errs += e
        name = rec.get("name")
        if name and not VI_ONLY.search(name) and (m.get("label_lang") != "en" or lang == "en"):
            continue  # module dung ten da dich lam nhan
        g = kho.grammar(gid)
        txt = kho.grammar_text(gid, lang)
        todo[str(gid)] = {"label": m["short_label"], "name": g.name, "pattern": g.pattern or None,
                          "meaning": (rec.get("meaning") or txt.get("meaning") or "")[:200] or None}
    return todo, errs, used


def publish(ws: Path, data_dir: Path, lang: str) -> tuple[dict, list[str]]:
    kho = Kho(data_dir)
    merged, st = merge_lang(ws, lang)
    out, stale = {}, 0
    for gid, rec in merged.items():
        g = kho.grammar(int(gid))
        cur = build_item(g, kho) if g is not None and canon_id(g.id) == g.id else None
        if cur is None or cur["src_hash"] != (rec.get("_meta") or {}).get("src_hash"):
            stale += 1
            continue
        meta = {k: rec["_meta"].get(k) for k in KEEP_META}
        out[gid] = {**{k: v for k, v in rec.items() if k != "_meta" and v not in (None, [], "")}, "_meta": meta}
    lp = ws / "labels" / f"{lang}.json"
    labels = read_json(lp) if lp.exists() else {}
    todo, errs, used = build_labels(kho, out, labels, lang)
    tp = ws / "labels" / f"{lang}.todo.json"
    if todo or tp.exists():  # het viec thi ghi "items": {} (khong xoa file)
        write_json(tp, {"_note": f"Nhan ngan can dich sang {lang}: dich 'label' (giu nguyen chu Nhat, ky hieu, "
                                 f"ngan nhu nhan goc), ghi vao labels/{lang}.json dang {{id: nhan}}, roi chay lai "
                                 f"publish_lang.py {lang}.", "items": todo})
    out = dict(sorted(out.items(), key=lambda kv: int(kv[0])))
    dest = data_dir / "grammar" / f"grammar_text.{lang}.json"
    write_json(dest, out, indent=None)
    if (ws / "particles" / f"{lang}.json").exists():
        e, n = export_particles(ws, lang)
        errs += e
        st["particles"] = n
    canon = sum(1 for g in kho.grammars.values() if canon_id(g.id) == g.id)
    st.update(written=sum(1 for v in out.values() if set(v) - {"short_label", "_meta"}), canon=canon,
              stale_now=stale, labels_used=used, labels_todo=len(todo), dest=str(dest))
    return st, errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lang", choices=[x for x in LANGS])
    ap.add_argument("--ws", help="thu muc translation/ (mac dinh <BUNPO_DATA_DIR>/translation)")
    ap.add_argument("--data", help="thu muc kho (mac dinh BUNPO_DATA_DIR)")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    data_dir = Path(a.data) if a.data else Path(get_settings().data_dir)
    st, errs = publish(ws, data_dir, a.lang)
    print(f"{a.lang}: {st['written']}/{st['canon']} mau co ban dich -> {st['dest']}")
    print(f"  lo da gop {st['batches']}/{st['of']}; bo qua: lech nguon luc dong goi {st['stale']}, "
          f"kho da sua sau dong goi {st['stale_now']} (dung tieng Viet, can dich bu)")
    print(f"  nhan ngan: {st['labels_used']} tu labels/{a.lang}.json, con {st['labels_todo']} chua dich"
          + (f" -> labels/{a.lang}.todo.json" if st["labels_todo"] else ""))
    if "particles" in st:
        print(f"  bang tro tu: {st['particles']} muc -> tables/particle_table.{a.lang}.json")
    for e in errs[:20]:
        print("  LOI " + e)
    print("Khoi dong lai server / tien trinh dung module de nap ban moi.")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
