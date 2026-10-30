"""Buoc 3.1: ham cham + script eval (LLM gia, khong goi mang)."""

import asyncio
import copy
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.config import Settings  # noqa: E402
from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.llm import LLMClient  # noqa: E402
from bunpo_analyzer.core.matcher import get_matcher  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402
from bunpo_analyzer.evaluation import (check_status, example_items, kho_examples, latency_stats,  # noqa: E402
                                       score_grammar, score_structure)
from tests.test_assemble import kho  # noqa: E402,F401
from tests.test_cache import Script  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD = {g["id"]: g for g in json.loads((ROOT / "tests" / "golden" / "golden_set.json").read_text(encoding="utf-8"))["items"]}


def _load_eval():
    spec = importlib.util.spec_from_file_location("eval_script", ROOT / "scripts" / "eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _g02_nodes(main=True):
    # 昨日0 友達1 と2 見3 た4 映画5 は6 とても7 面白かっ8 た9 です10 。11
    return [
        {"id": "g1", "type": "group", "parent": None, "kind": "rel", "span": [0, 5], "grammar": [196]},
        {"id": "r1", "type": "row", "parent": "g1", "role": "subject", "hidden": True, "span": None, "grammar": []},
        {"id": "r2", "type": "row", "parent": "g1", "role": "adv_time", "span": [0, 1], "grammar": []},
        {"id": "r3", "type": "row", "parent": "g1", "role": "complement", "span": [1, 3], "grammar": [19]},
        {"id": "r4", "type": "row", "parent": "g1", "role": "predicate", "span": [3, 5], "grammar": []},
        {"id": "r5", "type": "row", "parent": None, "role": "topic", "span": [5, 7], "grammar": [22]},
        {"id": "r6", "type": "row", "parent": None, "role": "predicate", "span": [7, 11], "main": main, "grammar": [43, 26]},
    ]


def test_score_structure_perfect_and_wrong():
    text = GOLD["G02"]["text"]
    toks = tokenize(text)
    ms = get_matcher().match(toks)
    s = score_structure(text, [t.surface for t in toks], _g02_nodes(), GOLD["G02"], ms)
    assert s["rows"][:2] == (5, 5) and s["groups"][:2] == (1, 1) and s["must"] == (4, 4)
    assert s["coverage_ok"] and s["extra"] == []  # 22 (は) la tro tu co ban, khong tinh thua
    s = score_structure(text, [t.surface for t in toks], _g02_nodes(main=False), GOLD["G02"], ms)
    assert s["rows"][0] == 4 and ("MAIN", "とても面白かったです") in s["missing_rows"]


def test_score_grammar_alternatives():
    gold = {"expect": {"grammar_must": [[1, 2], 3], "grammar_ok": [4]}}
    s = score_grammar({2, 4, 99}, gold, [])
    assert s["must"] == (1, 2) and s["missed"] == [3] and s["extra"] == [99]


def test_check_status():
    ok, _ = check_status(GOLD["G44"], {"error": {"code": "invalid_input", "reason": "multiple_sentences"}})
    assert ok
    ok, note = check_status(GOLD["G44"], {"error": {"code": "invalid_input", "reason": "too_long"}})
    assert not ok and "too_long" in note
    g31 = GOLD["G31"]
    good = {"error": {"code": "grammar_error"}, "input_check": {"status": "error", "correction": g31["expect"]["correction"],
                                                                "correction_at": [5, 10]}}
    assert check_status(g31, good)[0]
    bad = copy.deepcopy(good)
    bad["input_check"]["correction"] = "映画は面白かった。"
    assert not check_status(g31, bad)[0]
    assert check_status(GOLD["G40"], {"input_check": {"status": "suspect"}})[0]  # ok hoac suspect
    assert not check_status(GOLD["G02"], {"error": {"code": "structure_failed"}})[0]
    ok, note = check_status(GOLD["G21"], {"input_check": {"status": "ok"}})  # thieu auto_fix
    assert not ok and "auto_fix" in note


def test_example_items_and_sampling(kho):
    items = example_items("1. ①マンガを読みます。\n②日本語をべんきょうします。\nA: Tôi đọc truyện\n"
                          "2. A:　田中さんの　カメラは　どんな　カメラですか。\nB:　たかい　カメラです。")
    assert items == [["マンガを読みます。"], ["日本語をべんきょうします。"], ["田中さんのカメラはどんなカメラですか。", "たかいカメラです。"]]
    g = kho.grammars[19]
    raw = dict(g.raw, examples="1. 姉とケーキを作りました。\nTôi làm bánh với chị.")
    kho.grammars[19] = type(g)(**{**g.__dict__, "raw": raw})
    ex = kho_examples(kho, ["N5"], 5)
    assert [(e.grammar_id, e.text) for e in ex] == [(19, "姉とケーキを作りました。")]


def test_latency_stats():
    assert latency_stats([100, 300, 200, 1000]) == {"avg": 400, "p50": 300, "p95": 1000, "max": 1000}
    assert latency_stats([])["max"] == 0


async def test_eval_run_and_report(kho):
    ev = _load_eval()
    s = Settings(_env_file=None, openai_api_key="k", llm_model="main", llm_fallback_model="fb", llm_max_retries=0)
    good = P.fewshot_outputs()[0]
    broken = copy.deepcopy(good)
    broken["nodes"] = [n for n in broken["nodes"] if n["id"] != "r5"]
    sem = asyncio.Semaphore(2)
    g_inv = {"set": "golden", "id": "G46", "text": GOLD["G46"]["text"], "gold": GOLD["G46"]}
    r_inv = await ev.run_one(g_inv, s, kho, sem, LLMClient(Script([]), s, retry_delay_s=0))
    assert r_inv["status_ok"] and not r_inv["llm"]
    k_item = {"set": "kho", "id": "K19", "text": P.EX1_TEXT, "grammar_id": 19, "level": "N5"}
    r_k = await ev.run_one(k_item, s, kho, sem, LLMClient(Script([broken, good]), s, retry_delay_s=0))
    assert r_k["rule_hit"] and r_k["llm_hit"] and not r_k["first_ok"] and len(r_k["attempts"]) == 2
    k_miss = dict(k_item, id="K43x", grammar_id=999)
    r_m = await ev.run_one(k_miss, s, kho, sem, LLMClient(Script([good]), s, retry_delay_s=0))
    summ = ev.summarize([r_inv, r_k, r_m])
    assert summ["status"] == (1, 1) and summ["pick"] == (1, 2) and summ["first"] == (1, 2) and summ["fallback"] == 1
    table = ev.fmt("main", summ)
    assert any("Kho: LLM chọn đúng mẫu" in k for k in table)
    probs = ev.problems([r_inv, r_k, r_m])
    assert any("K43x" in p and "luật không bắt #999" in p for p in probs)
    assert any("K19" in p and "lần đầu sai khuôn" in p for p in probs)


def test_example_markers_fragments_and_pattern_equivalence(kho):
    from bunpo_analyzer.evaluation import _fragment, equivalents

    assert example_items("➂病気がなおったら、食べられるようになるでしょう。") == [["病気がなおったら、食べられるようになるでしょう。"]]
    assert _fragment("きのう買った本") and not _fragment("あしたは８時半に来てください")
    g = kho.grammars[43]
    kho.grammars[900] = type(g)(**{**g.__dict__, "id": 900, "name": "khác", "pattern": "～なくてはいけない/～ないといけない"})
    kho.grammars[901] = type(g)(**{**g.__dict__, "id": 901, "name": "khác 2", "pattern": "～ないといけない"})
    assert 901 in equivalents([], kho)[900]


def test_single_examples_skip_notes(kho):
    from bunpo_analyzer.evaluation import single_examples

    g = kho.grammars[19]
    raw = dict(g.raw, examples="1. 妻「会社の高橋さんからお電話よ\n2. 父（怒って）姉と話す。\n3. 姉と作りました。")
    g2 = type(g)(**{**g.__dict__, "raw": raw})
    assert single_examples(g2) == ["姉と作りました。"]
