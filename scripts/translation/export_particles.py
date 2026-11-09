"""E1: dua ban dich bang tro tu (translation/particles/<lang>.json, soan o C2) vao module.

    python scripts/translation/export_particles.py                 # en,id,tw,cn,ko
    python scripts/translation/export_particles.py --langs en --ws ../translation

Ghi src/bunpo_analyzer/tables/particle_table.<lang>.json dang {key: text} (lookup.table_meaning doc).
Chi ghi khi khong loi:
- du khoa cua bang module, khong khoa la;
- chu tieng Viet o translation/source/particle_table.json trung voi bang module (bang module sua sau
  khi dich -> ban dich cu, phai dich lai muc do);
- check_particles (finalize_glossary) khong loi: khong sot chu Viet, giu chu Nhat / ～ / ngoac.
Chi doc translation/, khong ghi vao do. Chay lai bat ky luc nao (sau khi sua bang tro tu / ban dich).
Ma thoat 1 neu co loi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_json, workspace, write_json
from finalize_glossary import check_particles

TABLES = Path(__file__).resolve().parents[2] / "src" / "bunpo_analyzer" / "tables"
DEFAULT_LANGS = "en,id,tw,cn,ko"


def export_lang(ws: Path, lang: str, tables: Path = TABLES) -> tuple[list[str], int]:
    mod = read_json(tables / "particle_table.json")["entries"]
    src = {e["key"]: e["vi"] for e in read_json(ws / "source" / "particle_table.json")["entries"]}
    p = ws / "particles" / f"{lang}.json"
    if not p.exists():
        return [f"{lang}: thieu particles/{lang}.json"], 0
    tr = read_json(p)
    errs = []
    for e in mod:
        if e["key"] not in src:
            errs.append(f"{lang}: muc moi chua dich {e['key']}")
        elif src[e["key"]] != e["vi"]:
            errs.append(f"{lang}: {e['key']} da sua tieng Viet sau khi dich, can dich lai")
        if not str(tr.get(e["key"]) or "").strip():
            errs.append(f"{lang}: thieu ban dich {e['key']}")
    extra = set(tr) - {e["key"] for e in mod}
    if extra:
        errs.append(f"{lang}: khoa la {sorted(extra)[:5]}")
    errs += check_particles(ws, lang)[0]
    if errs:
        return errs, 0
    out = {e["key"]: tr[e["key"]].strip() for e in mod}
    write_json(tables / f"particle_table.{lang}.json", out)
    return [], len(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws")
    ap.add_argument("--langs", default=DEFAULT_LANGS)
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    bad = 0
    for lang in [x.strip() for x in a.langs.split(",") if x.strip()]:
        errs, n = export_lang(ws, lang)
        if errs:
            bad += 1
            print(f"{lang}: {len(errs)} loi, khong ghi")
            for e in errs[:10]:
                print("  " + e)
        else:
            print(f"{lang}: {n} muc -> tables/particle_table.{lang}.json")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
