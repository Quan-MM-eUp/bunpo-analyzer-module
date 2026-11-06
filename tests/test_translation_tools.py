"""Bo cong cu dich kho (scripts/translation): manifest/khoa, kiem tra tang 1, gop, dong goi."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "translation"
sys.path.insert(0, str(TOOLS))

import check
import common
import merge
import tm

SRC_ITEMS = [
    {"id": 1618, "level": "N5", "context": {}, "fields": {
        "name": {"src": "vi", "text": "まだ（tiếp diễn tới khi hoàn tất）", "mode": "vi_parts"},
        "meaning": {"src": "vi", "text": "Diễn đạt sự liên tục"},
        "examples": [{"jp": "雨は、まだ二、三日続くだろう。", "vi": "Mưa có lẽ còn kéo dài."}],
        "explain": {"src": "ja", "text": "現在の状態がこれからも続く様子を表す。"},
        "mistakes": [{"src": "vi", "text": "× まだ食べる → ○ もう食べた"}],
        "comparison": {"headers": ["Mẫu", "Ý nghĩa"],
                       "rows": [["<ruby>遊<rt>あそ</rt></ruby>び", "chơi đùa"], ["〜ている", ""]]},
    }},
    {"id": 7, "level": "N5", "context": {}, "fields": {
        "meaning": {"src": "vi", "text": "Dùng 〜てから để nói thứ tự hành động"},
        "connection": {"src": "vi", "text": "Vて + から (sau khi)", "mode": "vi_parts"},
    }},
]
for _it in SRC_ITEMS:
    _it["src_hash"] = common.src_hash(_it["fields"])

GOOD_EN = {
    1618: {"name": "まだ (continuing until completion)", "meaning": "Expresses continuation",
           "examples": ["The rain will probably continue for two or three more days."],
           "explain": "Expresses that the current state will continue from now on.",
           "mistakes": ["× まだ食べる → ○ もう食べた"],
           "comparison": {"headers": ["Pattern", "Meaning"],
                          "rows": [["<ruby>遊<rt>あそ</rt></ruby>び", "play"], ["〜ている", ""]]}},
    7: {"meaning": "Uses 〜てから to state the order of actions", "connection": "Vて + から (after doing)"},
}


@pytest.fixture
def ws(tmp_path):
    common.write_json(tmp_path / "source" / "b001.json", {"batch": "b001", "items": SRC_ITEMS})
    common.write_json(tmp_path / "source" / "index.json", {"kho_version": "x", "batches": [
        {"batch": "b001", "items": 2, "chars": 100, "levels": ["N5"], "ids": [1618, 7], "hash": "h1"},
        {"batch": "b002", "items": 0, "chars": 0, "levels": [], "ids": [], "hash": "h2"}]})
    tm.init_manifests(tmp_path, ["en", "ko"])
    return tmp_path


def _write_out(ws, lang, fields_by_id, **extra):
    items = [{"id": it["id"], "src_hash": it["src_hash"], "fields": fields_by_id[it["id"]], **extra}
             for it in SRC_ITEMS if it["id"] in fields_by_id]
    common.write_json(ws / "out" / lang / "b001.json",
                      {"batch": "b001", "lang": lang, "model": "m", "prompt_ver": "1", "items": items})


# ---------------- common ----------------
def test_detectors():
    assert common.has_vi("Diễn đạt") and not common.has_vi("まだ")
    assert common.is_ja_only("現在の状態") and not common.is_ja_only("まだ (tiếp)")
    assert common.jp_runs("Dùng 〜てから để nói") == ["〜てから"]
    assert common.deruby("<ruby>遊<rt>あそ</rt></ruby>び") == "遊び"
    assert not common.VI_ONLY.search("Élève, Straße, łódź, ação")  # chu cai Phap/Duc/Ba Lan/Bo khong bi coi la tieng Viet
    assert common.VI_ONLY.search("được")
    assert common.src_hash({"a": 1, "b": 2}) == common.src_hash({"b": 2, "a": 1})


# ---------------- manifest / khoa ----------------
def test_init_keeps_status_and_resets_changed(ws):
    tm.mark(ws, "en", ["b001", "b002"], "passed", score="95")
    idx = common.read_json(ws / "source" / "index.json")
    idx["batches"][1]["hash"] = "h2-new"
    common.write_json(ws / "source" / "index.json", idx)
    info = tm.init_manifests(ws, ["en"])
    rows = {r["batch"]: r for r in tm.load_manifest(ws, "en")}
    assert info["en"]["changed"] == 1
    assert rows["b001"]["status"] == "passed" and rows["b001"]["score"] == "95"
    assert rows["b002"]["status"] == "pending" and rows["b002"]["note"] == "nguon doi"


def test_lock_claim_release_and_stale(ws):
    assert tm.claim(ws, "en", "A")
    assert not tm.claim(ws, "en", "B")
    assert tm.claim(ws, "en", "A")  # gia han
    assert not tm.release(ws, "en", "B")
    assert tm.release(ws, "en", "A")
    assert (ws / "locks" / "en.lock").exists()  # tra khoa = ghi de, khong xoa
    assert tm.claim(ws, "en", "B")
    lk = common.read_json(ws / "locks" / "en.lock")
    lk["ts"] = time.time() - common.LOCK_STALE_S - 10
    common.write_json(ws / "locks" / "en.lock", lk)
    assert tm.lock_holder(ws, "en") is None
    assert tm.claim(ws, "en", "C")


def test_auto_pick_and_next(ws):
    assert tm.auto_pick(ws, "A") == "en"
    tm.claim(ws, "en", "A")
    assert tm.auto_pick(ws, "A") == "en"  # uu tien ngon ngu minh dang giu
    assert tm.auto_pick(ws, "B") == "ko"
    tm.mark(ws, "en", ["b001"], "failed")
    assert [r["batch"] for r in tm.todo(tm.load_manifest(ws, "en"))] == ["b001", "b002"]
    tm.mark(ws, "en", ["b001"], "failed"); tm.mark(ws, "en", ["b001"], "failed")
    assert [r["batch"] for r in tm.todo(tm.load_manifest(ws, "en"))] == ["b002"]  # het luot


def test_cli_exit_codes(ws, capsys):
    assert tm.main(["--ws", str(ws), "claim", "en", "--who", "A"]) == 0
    assert tm.main(["--ws", str(ws), "claim", "en", "--who", "B"]) == 2
    assert "BUSY en A" in capsys.readouterr().out
    assert tm.main(["--ws", str(ws), "mark", "en", "b009", "--status", "passed"]) == 1
    with pytest.raises(ValueError):
        tm.mark(ws, "en", ["b001"], "done")


# ---------------- kiem tra tang 1 ----------------
def test_check_good(ws):
    _write_out(ws, "en", GOOD_EN, qa={"judge": "j", "score": 96, "qa": "ok"})
    r = check.check_batch(ws, "en", "b001")
    assert r["errors"] == [], r["errors"]


@pytest.mark.parametrize("patch, needle", [
    (lambda f: f[1618].update(meaning="Diễn đạt sự liên tục"), "chu tieng Viet"),
    (lambda f: f[7].update(meaning="Uses te kara to state the order of actions"), "mat chu Nhat"),
    (lambda f: f[1618].update(explain="現在の状態がこれからも続く様子を表す。"), "chua dich"),
    (lambda f: f[1618].update(examples=[]), "so cau"),
    (lambda f: f[1618].update(mistakes=[]), "so muc"),
    (lambda f: f[1618]["comparison"]["rows"].pop(), "kich thuoc bang"),
    (lambda f: f[1618]["comparison"]["rows"][0].__setitem__(0, "遊び"), "giu nguyen"),
    (lambda f: f[1618]["comparison"]["headers"].__setitem__(1, "<ruby>意<rt>い</rt></ruby> Meaning"), "furigana"),
    (lambda f: f[7].pop("connection"), "thieu"),
    (lambda f: f[7].update(extra="x"), "truong thua"),
    (lambda f: f.pop(7), "thieu muc"),
])
def test_check_errors(ws, patch, needle):
    f = json.loads(json.dumps(GOOD_EN))
    f = {int(k): v for k, v in f.items()}
    patch(f)
    _write_out(ws, "en", f)
    r = check.check_batch(ws, "en", "b001")
    assert any(needle in e for e in r["errors"]), r["errors"]


def test_check_script_and_variant(ws):
    ko = {1618: {**GOOD_EN[1618], "meaning": "This sentence is English not Korean at all, long enough to judge"},
          7: GOOD_EN[7]}
    _write_out(ws, "ko", ko)
    r = check.check_batch(ws, "ko", "b001")
    assert any("sai he chu" in e for e in r["errors"])
    err, _ = check.check_text("Dùng để nói thứ tự", "這個說語時們動詞問題對", "cn", "vi", "x", [])
    assert any("bien the" in e for e in err)
    err, _ = check.check_text("Dùng để nói thứ tự", "这个说语时们动词问题对", "cn", "vi", "x", [])
    assert not any("bien the" in e for e in err)


def test_check_glossary_and_missing_file(ws):
    common.write_json(ws / "glossary" / "en.json", {"terms": [{"vi": ["liên tục"], "tr": "continuation", "accept": []}]})
    f = {int(k): v for k, v in json.loads(json.dumps(GOOD_EN)).items()}
    f[1618]["meaning"] = "Expresses persistence"
    _write_out(ws, "en", f)
    r = check.check_batch(ws, "en", "b001")
    assert any("thuat ngu" in w for w in r["warnings"])
    assert check.check_batch(ws, "ko", "b001")["errors"] == ["chua co file dich"]


# ---------------- gop ----------------
def test_merge(ws):
    _write_out(ws, "en", GOOD_EN, qa={"judge": "j", "score": 80, "qa": "low", "issues": ["x"]})
    data, st = merge.merge_lang(ws, "en")
    assert data == {} and st["batches"] == 0  # chua dat thi chua gop
    tm.mark(ws, "en", ["b001"], "qa_low")
    data, st = merge.merge_lang(ws, "en")
    assert st["items"] == 2 and st["qa_low"] == 2
    r = data["1618"]
    assert r["examples"] == [{"jp": "雨は、まだ二、三日続くだろう。",
                              "tr": "The rain will probably continue for two or three more days."}]
    assert r["connection"] is None and r["notes"] is None
    assert r["_meta"]["qa"] == "low" and r["_meta"]["model"] == "m"
    assert data["7"]["connection"] == "Vて + から (after doing)" and data["7"]["examples"] == []
    assert list(data) == ["7", "1618"]


# ---------------- dong goi (kho that) ----------------
def _kho_dir():
    base = Path(os.environ.get("BUNPO_DATA_DIR", Path(__file__).resolve().parents[2]))
    return base if (base / "grammar" / "grammar_lib.json").exists() else None


@pytest.mark.kho
def test_export_real_kho():
    if _kho_dir() is None:
        pytest.skip("khong tim thay kho du lieu")
    import export_batches as eb

    from bunpo_analyzer.core.data import get_kho
    kho = get_kho(_kho_dir())
    it = eb.build_item(kho.grammars[1618], kho)
    assert set(it["fields"]) >= {"name", "meaning", "examples", "explain"}
    assert it["fields"]["explain"]["src"] == "ja" and it["fields"]["name"]["mode"] == "vi_parts"
    assert "connection" not in it["fields"]  # まだ + V/A: khong co chu Viet
    items = [{"fields": {"meaning": {"text": "x" * 6000}}}] * 9
    bs = eb.make_batches(items, target=20000)
    assert [len(b) for b in bs] == [3, 3, 3]


# ---------------- C2: bang thuat ngu, bang tro tu ----------------
def test_glossary_longest_first_and_nocheck():
    g = [{"vi": ["danh từ"], "tr": "noun", "check": True},
         {"vi": ["danh từ hóa"], "tr": "nominaliz", "check": True},
         {"vi": ["sai"], "tr": "incorrect", "check": False}]
    _, w = check.check_text("Danh từ hóa là sai", "Nominalization is wrong", "en", "vi", "x", g)
    assert w == []
    _, w = check.check_text("đây là danh từ", "this is a name", "en", "vi", "x", g)
    assert w == ["x: thuat ngu 'danh từ' nen dich 'noun'"]


def test_finalize_glossary_and_particles(tmp_path):
    import finalize_glossary as fg
    common.write_json(tmp_path / "glossary" / "_source.json", {"terms": [
        {"id": "noun", "cat": "pos", "vi": ["danh từ"], "ja": "名詞", "hint": "noun", "freq": 3, "check": True},
        {"id": "te_form", "cat": "form", "vi": ["thể て"], "ja": "て形", "hint": "te-form", "freq": 1, "check": True}]})
    common.write_json(tmp_path / "glossary" / "en.json", {"lang": "en", "terms": {
        "noun": {"tr": "noun", "accept": ["nouns", "noun"]}, "te_form": {"tr": "te-form"}}})
    errs, n = fg.finalize_glossary(tmp_path, "en")
    assert errs == [] and n == 2
    g = common.read_json(tmp_path / "glossary" / "en.json")["terms"]
    assert g[0] == {"id": "noun", "cat": "pos", "vi": ["danh từ"], "ja": "名詞", "tr": "noun", "accept": ["nouns"],
                    "note": "", "check": True}
    assert fg.finalize_glossary(tmp_path, "en")[0] == []  # chay lai van on
    common.write_json(tmp_path / "glossary" / "ko.json", {"terms": {"noun": {"tr": "danh từ"}}})
    errs, _ = fg.finalize_glossary(tmp_path, "ko")
    assert any("te_form" in e for e in errs) and any("chu Viet" in e for e in errs)

    common.write_json(tmp_path / "source" / "particle_table.json", {"entries": [
        {"key": "te_shireru", "base": "しれる", "vi": "(～かもしれない: có lẽ, có thể)"},
        {"key": "prt_は", "base": "は", "vi": "chủ đề"}]})
    common.write_json(tmp_path / "particles" / "en.json", {"te_shireru": "(～かもしれない: maybe, might)", "prt_は": "topic"})
    assert fg.check_particles(tmp_path, "en")[0] == []
    common.write_json(tmp_path / "particles" / "en.json", {"te_shireru": "(maybe, might)", "prt_は": "chủ đề"})
    errs = fg.check_particles(tmp_path, "en")[0]
    assert any("mat chu Nhat" in e for e in errs) and any("chu tieng Viet" in e for e in errs)


def test_brief_lists_only_batch_terms(ws, capsys):
    import brief
    common.write_json(ws / "glossary" / "en.json", {"terms": [
        {"id": "noun", "vi": ["danh từ"], "ja": "名詞", "tr": "noun", "accept": ["nouns"], "note": ""},
        {"id": "verb", "vi": ["động từ"], "ja": "動詞", "tr": "verb", "accept": [], "note": ""},
        {"id": "te", "vi": ["thể て"], "ja": "て形", "tr": "te-form", "accept": [], "note": ""}]})
    common.write_json(ws / "source" / "b001.json", {"batch": "b001", "items": [
        {"id": 1, "fields": {"meaning": {"src": "vi", "text": "Dùng sau danh từ"},
                             "examples": [{"jp": "x", "vi": "động từ"}]}}]})
    assert [t["id"] for t in brief.terms_for(ws, "en", "b001")] == ["noun"]  # cau vi du khong tinh
    brief.main(["--ws", str(ws), "en", "b001"])
    assert "danh từ (名詞) → noun  (also: nouns)" in capsys.readouterr().out


def test_export_junk_and_english():
    import export_batches as eb
    eb.DATA_ISSUES.clear()
    assert eb._text_field("*① 休みたければ休めばいい。\n#####\n② …", where="#1.meaning") is None
    assert eb.DATA_ISSUES and eb.DATA_ISSUES[0]["where"] == "#1.meaning"
    f = eb._text_field("ちがいます（否定返答） means The phrase is used to deny politely")
    assert f["src"] == "en"
    assert eb._text_field("現在の状態を表す。")["src"] == "ja"
    assert eb._text_field("Diễn đạt")["src"] == "vi"


def test_qa_apply_and_report(ws):
    import qa
    _write_out(ws, "en", GOOD_EN)
    res = [{"batch": "b001", "judge": "sonnet", "rounds": 1, "items": [
        {"id": 1618, "score": 99, "qa": "ok", "issues": [{"severity": "minor", "note": "x"}]},
        {"id": 7, "score": 90, "qa": "fix", "issues": [{"severity": "major", "note": "y"}, {"severity": "minor"}]}]},
        {"batch": "b002", "items": []}]
    common.write_json(ws / "res.json", res)
    assert qa.main(["--ws", str(ws), "en", "--results", str(ws / "res.json")]) == 0
    rep = common.read_json(ws / "reports" / "en" / "last_round.json")
    b1, b2 = rep["batches"]
    assert b1["status"] == "qa_low" and b1["low_ids"] == [7] and b1["score"] == 94.5
    assert b2["status"] == "failed"  # chua co file dich
    out = {i["id"]: i["qa"] for i in common.read_json(ws / "out" / "en" / "b001.json")["items"]}
    assert out[1618] == {"judge": "sonnet", "score": 99, "qa": "ok", "issues": []}
    assert out[7]["qa"] == "low" and out[7]["issues"] == [{"severity": "major", "note": "y"}]
    assert check.check_batch(ws, "en", "b001")["errors"] == []
    assert (ws / "reports" / "en" / "last_round.md").exists()
    tm.apply_report(ws, rep, who="A")
    rows = {r["batch"]: r for r in tm.load_manifest(ws, "en")}
    assert rows["b001"]["status"] == "qa_low" and rows["b001"]["qa_low"] == "1" and rows["b001"]["score"] == "94.5"
    assert rows["b002"]["status"] == "failed" and rows["b002"]["attempts"] == "1"
