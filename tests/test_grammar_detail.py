"""Buoc 4.2: du lieu bang ngu phap (examples_clean, mistakes, comparison, grammar_detail)."""

import json
from pathlib import Path

from bunpo_analyzer.core.data import Kho
from bunpo_analyzer.core.grammar_detail import comparison, examples_clean, grammar_detail, mistakes


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


EX = """1. この 歌は 聞いた ことが あります。
Tôi từng nghe bài hát này.
2. A:　どうして？
B:　富士山に 登った ことが ありますか。
A: Tại sao?
B: Anh đã bao giờ leo núi Phú Sĩ chưa.

──────

1. ①　この歌は聞いたことがあります。
Trùng câu trên.
2. ➂　雪を見たことがありません。
Tôi chưa từng thấy tuyết."""


def test_examples_clean():
    ex = examples_clean(EX)
    assert [e.jp for e in ex] == ["この歌は聞いたことがあります。", "雪を見たことがありません。",
                                  "A: どうして？\nB: 富士山に登ったことがありますか。"]
    assert ex[0].vi == "Tôi từng nghe bài hát này." and not ex[0].dialog and ex[2].dialog
    assert ex[2].vi == "A: Tại sao?\nB: Anh đã bao giờ leo núi Phú Sĩ chưa."
    assert examples_clean("[]") == [] and examples_clean(None) == []
    assert len(examples_clean(EX, limit=1)) == 1


def test_mistakes():
    assert mistakes("• Quên な: 静かので× → 静かなので✓\n\n- Dùng sai\n1. Ba\n• Quên な: 静かので× → 静かなので✓") == \
        ["Quên な: 静かので× → 静かなので✓", "Dùng sai", "Ba"]


def test_comparison_table():
    html = ("<table border='1'><thead><tr><th>Mẫu</th><th>Ví dụ</th></tr></thead><tbody>"
            "<tr><td>Vてから</td><td><ruby>読<rt>よ</rt></ruby>んでから、<b>書</b>く。<script>x</script></td></tr></tbody></table>")
    c = comparison(html)
    assert c.headers == ["Mẫu", "Ví dụ"]
    assert c.rows == [["Vてから", "<ruby>読<rt>よ</rt></ruby>んでから、書く。x"]]
    assert comparison("") is None and comparison("không phải bảng") is None


def test_grammar_detail(tmp_path):
    _write(tmp_path / "word" / "word_lib.json", [])
    _write(tmp_path / "grammar" / "grammar_lib.json", [
        {"id": 252, "grammar": "～た　ことが　ある", "grammar_reading": "", "pattern": "～たことがある", "level": "N4",
         "接続": "Vた + ことがある", "meaning_vi": "Đã từng…", "examples": EX, "explain": "Giải thích.",
         "comparison": "<table><tr><th>A</th></tr><tr><td>B</td></tr></table>",
         "common_mistakes": "• Lỗi 1\n• Lỗi 2", "notes": "Ghi chú.", "label": ["grammar_exper"],
         "confusable": "～た　ことが　ない"},
        {"id": 350, "grammar": "～た　ことが　ない", "pattern": "～たことがない", "level": "N4", "meaning_vi": "Chưa từng",
         "examples": "", "接続": "", "label": []},
    ])
    _write(tmp_path / "grammar" / "grammar_text.en.json", {"252": {"meaning": "Have done before", "mistakes": "• Mistake"}})
    _write(tmp_path / "i18n" / "en.json", {"label": {"grammar_exper": "experience"}})
    kho = Kho(tmp_path)
    d = grammar_detail(252, "vi", kho)
    assert (d.short_label, d.level, d.meaning, d.connection, d.text_lang) == ("～たことがある", "N4", "Đã từng…", "Vた + ことがある", "vi")
    assert d.examples[0].jp == "この歌は聞いたことがあります。" and d.mistakes == ["Lỗi 1", "Lỗi 2"]
    assert d.comparison.rows == [["B"]] and d.notes == "Ghi chú." and d.labels[0].code == "grammar_exper"
    assert [c.id for c in d.confusable] == [350] and d.confusable[0].short_label == "～たことがない"
    en = grammar_detail(252, "en", kho)
    assert (en.meaning, en.mistakes, en.text_lang, en.labels[0].name) == ("Have done before", ["Mistake"], "en", "experience")
    assert grammar_detail(999, "vi", kho) is None


def _kho_tr(tmp_path):
    """Kho nho co ban dich en: 252 (du truong), 30 (nhan chu Viet), 338 (mau chuan cua 220, trung da gom)."""
    _write(tmp_path / "word" / "word_lib.json", [])
    _write(tmp_path / "grammar" / "grammar_lib.json", [
        {"id": 252, "grammar": "～た　ことが　ある", "pattern": "～たことがある", "level": "N4",
         "接続": "Vた + ことがある (động từ)", "meaning_vi": "Đã từng…", "examples": EX, "explain": "Giải thích.",
         "comparison": "<table><tr><th>Mẫu</th></tr><tr><td>Đã</td></tr></table>",
         "common_mistakes": "• Lỗi 1\n• Lỗi 2", "notes": "Ghi chú.", "label": []},
        {"id": 30, "grammar": "～から（điểm xuất phát）", "pattern": "～から", "level": "N5", "meaning_vi": "Từ", "label": []},
        {"id": 338, "grammar": "～う／よう（thể ý chí）", "pattern": "～う", "level": "N4", "meaning_vi": "Hãy cùng",
         "examples": "1. 行こう。\nĐi thôi.", "label": []},
        {"id": 220, "grammar": "V thể ý chí", "pattern": "", "level": "N5", "meaning_vi": "Thể ý chí",
         "examples": "1. 帰ろう。\nVề thôi.", "label": []},
    ])
    _write(tmp_path / "grammar" / "grammar_text.en.json", {
        "252": {"meaning": "Have done before", "connection": "Vた + ことがある (verb)", "notes": "Note.",
                "examples": [{"jp": "この歌は聞いたことがあります。", "tr": "I have heard this song."}],
                "mistakes": ["• Mistake 1", "Mistake 2"],
                "comparison": {"headers": ["Pattern"], "rows": [["Did"]]}},
        "30": {"name": "～から（starting point）", "meaning": "From"},
        "338": {"name": "～う／よう（volitional form）", "short_label": "～う／よう (let's)", "meaning": "Let's",
                "examples": [{"jp": "行こう。", "tr": "Let's go."}]},
    })
    return Kho(tmp_path)


def test_grammar_detail_translated(tmp_path):
    kho = _kho_tr(tmp_path)
    en = grammar_detail(252, "en", kho)
    assert (en.text_lang, en.meaning, en.connection, en.notes) == ("en", "Have done before", "Vた + ことがある (verb)", "Note.")
    assert en.examples[0].tr == "I have heard this song." and en.examples[0].vi == "Tôi từng nghe bài hát này."
    assert all(e.tr == e.vi for e in en.examples[1:])  # chua dich cau nay -> dung tieng Viet
    assert en.mistakes == ["Mistake 1", "Mistake 2"] and en.comparison.headers == ["Pattern"]
    vi = grammar_detail(252, "vi", kho)
    assert vi.connection == "Vた + ことがある (động từ)" and vi.notes == "Ghi chú." and vi.examples[0].tr == vi.examples[0].vi
    assert vi.comparison.headers == ["Mẫu"] and vi.text_lang == "vi"
    ko = grammar_detail(252, "ko", kho)  # chua co ban dich ko
    assert ko.text_lang == "vi" and ko.meaning == "Đã từng…"


def test_short_label_and_duplicates(tmp_path):
    from bunpo_analyzer.core.grammar_meta import short_label

    kho = _kho_tr(tmp_path)
    assert short_label(30, kho, "vi") == "～から（điểm xuất phát）"
    assert short_label(30, kho, "en") == "～から（starting point）"  # ten da dich
    assert short_label(338, kho, "en") == "～う／よう (let's)"  # nhan dich tay uu tien
    assert short_label(220, kho, "en") == "～う／よう (let's)"  # mau trung -> nhan mau chuan
    assert short_label(220, kho, "vi") == "V thể ý chí"
    assert short_label(30, kho, "ko") == "～から（điểm xuất phát）"  # chua dich: nhan goc
    d = grammar_detail(220, "en", kho)  # mau trung chua dich rieng -> noi dung mau chuan, giu id
    assert d.id == 220 and d.meaning == "Let's" and d.examples[0].tr == "Let's go."
    assert grammar_detail(220, "vi", kho).meaning == "Thể ý chí"


def test_publish_labels(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "translation"))
    pytest = __import__("pytest")
    pytest.importorskip("sudachipy")
    import publish_lang as pl

    kho = _kho_tr(tmp_path)
    assert pl.label_errors("～から（điểm xuất phát）", "～から（starting point）", "x") == []
    assert pl.label_errors("～から（điểm xuất phát）", "(starting point)", "x")  # mat chu Nhat
    assert pl.label_errors("～から（điểm xuất phát）", "～から（điểm）", "x")  # con chu Viet
    out = {"30": {"name": "～から（starting point）"}, "338": {"meaning": "Let's"}}
    todo, errs, used = pl.build_labels(kho, out, {}, "en")
    assert list(todo) == ["338"] and errs == [] and used == 0  # 30 co ten dich, 220 la mau trung
    todo, errs, used = pl.build_labels(kho, out, {"338": "～う／よう (let's)", "30": "sai"}, "en")
    assert todo == {} and used == 1 and out["338"]["short_label"] == "～う／よう (let's)"
    assert any("[30]" in e for e in errs)  # nhan dich sai -> bao loi, van dung ten da dich
