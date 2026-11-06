"""Kiem tra tang 1 (code) cho ban dich (ke-hoach-dich-kho-ngu-phap.md, muc 5).

    python check.py [--ws DIR] <lang> b001 b002 ...     kiem tra cac lo
    python check.py [--ws DIR] <lang> --all             moi lo da co trong out/<lang>/
    them --json de in ket qua dang JSON (cho tac tu doc)

So out/<lang>/bNNN.json voi source/bNNN.json. File dich:
    {"batch": "b001", "lang": "en", "model": "...", "prompt_ver": "1", "date": "...",
     "items": [{"id": 1618, "src_hash": "...",
                "fields": {"name": "...", "meaning": "...", "connection": "...",
                           "examples": ["cau dich 1", ...],          # cung thu tu, cung so cau voi nguon
                           "explain": "...", "notes": "...",
                           "mistakes": ["...", ...],                  # cung so muc voi nguon
                           "comparison": {"headers": [...], "rows": [[...], ...]}},   # cung kich thuoc
                "qa": {"judge": "...", "score": 0-100, "qa": "ok|low", "issues": [...]}}]}   # tang 2, co the chua co
Loi (errors) -> lo phai dich lai; canh bao (warnings) -> tac tu cham xem lai.
Ma thoat: 0 khong loi, 1 co loi.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    KANA,
    LANGS,
    LATIN,
    PUNCT_SPACE,
    RUBY,
    SCRIPT,
    SIMPLIFIED_ONLY,
    SYMBOLS,
    TRADITIONAL_ONLY,
    VI_ONLY,
    deruby,
    has_vi,
    jp_runs,
    read_json,
    workspace,
)

TEXT_FIELDS = ("name", "meaning", "connection", "explain", "notes")
# ti le do dai ban dich / ban Viet chap nhan duoc (chi canh bao, chuoi nguon >= 60 ky tu)
LEN_RATIO = {"ko": (0.3, 1.3), "cn": (0.15, 0.85), "tw": (0.15, 0.85), "my": (0.6, 3.2),
             "hi": (0.5, 2.3), "ne": (0.5, 2.3), "th": (0.5, 2.2)}
LEN_RATIO_DEFAULT = (0.5, 2.1)


def _norm(s: str) -> str:
    return PUNCT_SPACE.sub("", (s or "").replace("〜", "～"))


def _word_in(w: str, text: str) -> bool:
    return re.search(r"(?<![\wà-ỹđ])" + re.escape(w) + r"(?![\wà-ỹđ])", text) is not None


def _letters(s: str) -> int:
    return sum(1 for ch in s if ch.isalpha())


def script_ratio(t: str, lang: str) -> float | None:
    """Ti le chu dung he chu cua ngon ngu dich tren tong so chu cai (bo cum tieng Nhat, ruby)."""
    s = RUBY.sub("", t)
    for r in jp_runs(s):
        s = s.replace(r, "")
    if lang in ("cn", "tw"):
        s = KANA.sub("", s)
    n = _letters(s)
    if n < 30:
        return None
    rx = SCRIPT.get(lang, LATIN)
    return len(rx.findall(s)) / n


# Ky hieu ngu phap viet bang chu Latin (khong phai loi van can dich)
NOTATION = {"na", "adj", "vt", "vi", "vn", "nb", "pp", "ok"}


def has_words(s: str) -> bool:
    """Co tu chu Latin that (>= 2 chu, khong phai ky hieu V/N/Na...): vd tieng Viet khong dau "cho", "Sau khi"."""
    return any(w.lower() not in NOTATION for w in re.findall(r"[A-Za-zÀ-ỹđĐ]{2,}", deruby(s or "")))


def check_text(s: str, t, lang: str, src: str, where: str, glossary: list[dict]) -> tuple[list, list]:
    err, warn = [], []
    if src == "ex":  # cau vi du: dich tu cau Nhat (co the co chu Latin nhu ICカード)
        src = "ja"
    elif src == "ja" and has_words(s):
        src = "vi"  # nguon "ja" nhung co loi Latin (vd "Sai chia: ×行くませんか → ✓…"): dich phan chu, giu chu Nhat
    if not isinstance(t, str) or not t.strip():
        return [f"{where}: rong / sai kieu"], []
    if VI_ONLY.search(t):
        err.append(f"{where}: con chu tieng Viet: {VI_ONLY.findall(t)[:5]}")
    # ruby giu nguyen tung chiec
    rs, rt = RUBY.findall(s), RUBY.findall(t)
    if sorted(rs) != sorted(rt):
        err.append(f"{where}: furigana <ruby> khong khop ({len(rs)} -> {len(rt)})")
    tn = _norm(deruby(t))
    if src in ("vi", "en"):
        miss = [r for r in jp_runs(deruby(s)) if _norm(r) not in tn]
        if miss:
            err.append(f"{where}: mat chu Nhat {miss[:4]}")
    elif t.strip() == s.strip() and any(m in s for m in "×○✕"):
        pass  # dong sua loi chi co chu Nhat (× … → ○ …): chep nguyen la dung
    else:  # nguon tieng Nhat: phai dich, khong chep lai
        kana = len(KANA.findall(RUBY.sub("", t)))
        lim = 0.15 if lang in ("cn", "tw") else 0.3
        if kana / max(len(_norm(t)), 1) > lim:
            err.append(f"{where}: chua dich (con nhieu kana)")
    r = script_ratio(t, lang)
    if r is not None:
        if r < 0.3:
            err.append(f"{where}: sai he chu ({lang}: {r:.0%})")
        elif r < 0.6:
            warn.append(f"{where}: it chu {lang} ({r:.0%})")
    for ch in SYMBOLS:
        if s.count(ch) != t.count(ch):
            warn.append(f"{where}: ky hieu {ch} {s.count(ch)} -> {t.count(ch)}")
    if lang in ("cn", "tw"):
        body = RUBY.sub("", t)
        for jr in jp_runs(body):
            body = body.replace(jr, "")
        simp = sum(body.count(c) for c in SIMPLIFIED_ONLY)
        trad = sum(body.count(c) for c in TRADITIONAL_ONLY)
        wrong, right = (trad, simp) if lang == "cn" else (simp, trad)
        if wrong >= 3 and right == 0:
            err.append(f"{where}: sai bien the chu Han ({'phon the' if lang == 'cn' else 'gian the'})")
        elif wrong > right:
            warn.append(f"{where}: nghi sai bien the chu Han ({wrong} > {right})")
    if src == "vi" and len(s) >= 60:
        lo, hi = LEN_RATIO.get(lang, LEN_RATIO_DEFAULT)
        k = len(t) / len(s)
        if not lo <= k <= hi:
            warn.append(f"{where}: do dai bat thuong x{k:.2f}")
    sl, tl = s.lower(), t.lower()
    # thuat ngu dai truoc (danh tu hoa truoc danh tu); khop roi thi xoa khoi ban nguon
    pairs = [(x.lower(), e) for e in glossary if e.get("check") is not False and e.get("tr")
             for x in e.get("vi", [])]
    for v, g in sorted(pairs, key=lambda x: -len(x[0])):
        # "chủ thể thường" khong phai "thể thường" (the thuong)
        pre = r"(?<!chủ )" if v.startswith("thể") else ""
        rx = re.compile(pre + r"(?<![\wà-ỹđ])" + re.escape(v) + r"(?![\wà-ỹđ])")
        if not rx.search(sl):
            continue
        sl = rx.sub(" ", sl)
        ok = [g["tr"], *g.get("accept", [])]
        if not any(o.lower() in tl for o in ok):
            warn.append(f"{where}: thuat ngu '{g['vi'][0]}' nen dich '{g['tr']}'")
    return err, warn


def check_item(si: dict, ti: dict, lang: str, glossary: list[dict]) -> tuple[list, list]:
    gid = si["id"]
    err, warn = [], []
    if ti.get("src_hash") != si["src_hash"]:
        err.append(f"#{gid}: src_hash khac nguon")
    sf, tf = si["fields"], ti.get("fields") or {}
    extra = set(tf) - set(sf)
    if extra:
        err.append(f"#{gid}: truong thua {sorted(extra)}")
    for k, sv in sf.items():
        w = f"#{gid}.{k}"
        tv = tf.get(k)
        if tv is None:
            err.append(f"{w}: thieu")
            continue
        if k in TEXT_FIELDS:
            e, wn = check_text(sv["text"], tv, lang, sv["src"], w, glossary)
        elif k == "examples":
            if not isinstance(tv, list) or len(tv) != len(sv):
                err.append(f"{w}: so cau {len(sv)} -> {len(tv) if isinstance(tv, list) else '?'}")
                continue
            e, wn = [], []
            for j, (ex, tr) in enumerate(zip(sv, tv)):
                # cau dich tu cau Nhat: kiem tra nhu nguon tieng Nhat (khong chep lai cau Nhat)
                a, b = check_text(ex["jp"], tr, lang, "ex", f"{w}[{j}]", [])
                e += a; wn += [x for x in b if "ky hieu" not in x]
        elif k == "mistakes":
            if not isinstance(tv, list) or len(tv) != len(sv):
                err.append(f"{w}: so muc {len(sv)} -> {len(tv) if isinstance(tv, list) else '?'}")
                continue
            e, wn = [], []
            for j, (m, tr) in enumerate(zip(sv, tv)):
                a, b = check_text(m["text"], tr, lang, m["src"], f"{w}[{j}]", glossary)
                e += a; wn += b
        elif k == "comparison":
            e, wn = check_table(sv, tv, lang, w, glossary)
        else:
            e, wn = [f"{w}: truong la"], []
        err += e; warn += wn
    q = ti.get("qa")
    if q is not None and (not isinstance(q, dict) or q.get("qa") not in ("ok", "low") or not isinstance(q.get("score"), (int, float))):
        err.append(f"#{gid}.qa: sai khuon (can judge, score, qa ok|low)")
    return err, warn


def check_table(sv: dict, tv, lang: str, w: str, glossary: list[dict]) -> tuple[list, list]:
    if not isinstance(tv, dict) or not isinstance(tv.get("headers"), list) or not isinstance(tv.get("rows"), list):
        return [f"{w}: sai khuon"], []
    if len(tv["headers"]) != len(sv["headers"]) or len(tv["rows"]) != len(sv["rows"]) \
            or any(len(a) != len(b) for a, b in zip(sv["rows"], tv["rows"])):
        return [f"{w}: kich thuoc bang khac nguon"], []
    err, warn = [], []
    cells = [("h", j, a, b) for j, (a, b) in enumerate(zip(sv["headers"], tv["headers"]))]
    cells += [(f"r{i}", j, a, b) for i, (ra, rb) in enumerate(zip(sv["rows"], tv["rows"])) for j, (a, b) in enumerate(zip(ra, rb))]
    for tag, j, a, b in cells:
        where = f"{w}[{tag}.{j}]"
        if not (a or "").strip():
            if (b or "").strip():
                warn.append(f"{where}: o rong ma ban dich co chu")
            continue
        if not has_vi(RUBY.sub("", a)) and not has_words(a):  # o chi co chu Nhat / ky hieu: giu nguyen
            if a != b:
                same = _norm(deruby(a)) == _norm(deruby(b or "")) and sorted(RUBY.findall(a)) == sorted(RUBY.findall(b or ""))
                (warn if same else err).append(f"{where}: o khong co chu Viet (giu nguyen) bi doi")
            continue
        e, wn = check_text(a, b, lang, "vi", where, glossary)
        err += e; warn += wn
    return err, warn


def check_batch(ws: Path, lang: str, batch: str) -> dict:
    src = read_json(ws / "source" / f"{batch}.json")
    p = ws / "out" / lang / f"{batch}.json"
    if not p.exists():
        return {"batch": batch, "errors": ["chua co file dich"], "warnings": [], "items": 0}
    try:
        out = read_json(p)
    except (OSError, ValueError) as e:  # JSON hong
        return {"batch": batch, "errors": [f"JSON hong: {e}"], "warnings": [], "items": 0}
    gl = []
    gp = ws / "glossary" / f"{lang}.json"
    if gp.exists():
        gl = read_json(gp).get("terms", [])
    err, warn = [], []
    if out.get("lang") not in (None, lang):
        err.append(f"lang trong file = {out.get('lang')}")
    tmap = {}
    for ti in out.get("items") or []:
        try:
            tmap[int(ti.get("id"))] = ti
        except (TypeError, ValueError):
            err.append(f"muc khong co id: {str(ti)[:60]}")
    sids = [si["id"] for si in src["items"]]
    miss = [i for i in sids if i not in tmap]
    extra = sorted(set(tmap) - set(sids))
    if miss:
        err.append(f"thieu muc {miss}")
    if extra:
        err.append(f"thua muc {extra}")
    bad_items = set()
    for si in src["items"]:
        ti = tmap.get(si["id"])
        if ti is None:
            continue
        e, w = check_item(si, ti, lang, gl)
        if e:
            bad_items.add(si["id"])
        err += e; warn += w
    return {"batch": batch, "items": len(sids), "bad_items": sorted(bad_items), "errors": err, "warnings": warn}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws")
    ap.add_argument("lang", choices=LANGS)
    ap.add_argument("batches", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    bs = a.batches
    if a.all:
        bs = sorted(p.stem for p in (ws / "out" / a.lang).glob("b*.json"))
    res = [check_batch(ws, a.lang, b) for b in bs]
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res:
            mark = "OK " if not r["errors"] else "LOI"
            print(f"{mark} {r['batch']}: {len(r['errors'])} loi, {len(r['warnings'])} canh bao")
            for e in r["errors"][:20]:
                print("   x", e)
            for w in r["warnings"][:10]:
                print("   !", w)
    return 1 if any(r["errors"] for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
