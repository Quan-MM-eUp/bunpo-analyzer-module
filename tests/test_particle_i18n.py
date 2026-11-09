"""E1: ban dich bang tro tu (tables/particle_table.<lang>.json) va script export_particles."""

import json
import sys
from pathlib import Path

import pytest

from bunpo_analyzer.core.lookup import _TABLES, table_meaning

LANGS = ("en", "id", "tw", "cn", "ko")
TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "translation"
VI = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"


def _load(name):
    return json.loads((_TABLES / name).read_text(encoding="utf-8"))


ENTRIES = _load("particle_table.json")["entries"]


@pytest.mark.parametrize("lang", LANGS)
def test_table_complete(lang):
    tr = _load(f"particle_table.{lang}.json")
    assert set(tr) == {e["key"] for e in ENTRIES}
    for k, v in tr.items():
        assert v.strip(), k
        assert not any(c in VI for c in v.lower()), f"{lang}.{k} con chu Viet: {v}"


@pytest.mark.parametrize("lang", LANGS)
def test_table_meaning_uses_lang(lang):
    e = next(x for x in ENTRIES if x["base"] == "そう")
    m = table_meaning(e, lang)
    assert m != e["vi"] and "～そうだ" in m
    assert table_meaning(e, "vi") == e["vi"]
    assert table_meaning(e, "fr") == e["vi"]  # chua dua vao module -> tieng Viet


def test_lookup_dict_particles_en():
    pytest.importorskip("sudachipy")
    import asyncio

    from bunpo_analyzer.core.dictionary import StaticDictionary
    from bunpo_analyzer.core.lookup import lookup_dict
    from bunpo_analyzer.core.tokenizer import tokenize

    toks = tokenize("雨が降りそうなので、傘を持っていきます。")
    res = asyncio.run(lookup_dict(toks, StaticDictionary({}), "en"))
    got = {t.surface: w for t, w in zip(toks, res.words)}
    for s in ("が", "そう", "を"):
        assert got[s].meaning_source == "particle_table"
        assert not any(c in VI for c in got[s].meaning.lower()), (s, got[s].meaning)


def _ws(tmp_path, tr, vi_override=None):
    src = [dict(e) for e in ENTRIES]
    if vi_override:
        src[0]["vi"] = vi_override
    (tmp_path / "ws" / "source").mkdir(parents=True)
    (tmp_path / "ws" / "particles").mkdir()
    (tmp_path / "ws" / "source" / "particle_table.json").write_text(
        json.dumps({"entries": src}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "ws" / "particles" / "en.json").write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "particle_table.json").write_text(json.dumps({"entries": ENTRIES}, ensure_ascii=False),
                                                encoding="utf-8")
    return tmp_path / "ws", tables


def test_export_script(tmp_path):
    sys.path.insert(0, str(TOOLS))
    import export_particles as ep

    good = _load("particle_table.en.json")
    ws, tables = _ws(tmp_path, good)
    assert ep.export_lang(ws, "en", tables) == ([], len(ENTRIES))
    assert json.loads((tables / "particle_table.en.json").read_text(encoding="utf-8")) == good

    bad = dict(good)
    bad.pop(ENTRIES[1]["key"])
    bad["la"] = "x"
    ws, tables = _ws(tmp_path / "b", bad, vi_override="nghĩa cũ")
    errs, n = ep.export_lang(ws, "en", tables)
    assert n == 0 and not (tables / "particle_table.en.json").exists()
    assert any("dich lai" in e for e in errs) and any("thieu ban dich" in e for e in errs)
    assert any("khoa la" in e for e in errs)
