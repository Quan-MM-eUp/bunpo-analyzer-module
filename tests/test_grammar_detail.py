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
