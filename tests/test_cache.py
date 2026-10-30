"""Buoc 2.6: cache + "dich nhe" (khong goi mang)."""

import asyncio
import copy

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer.config import Settings  # noqa: E402
from bunpo_analyzer.core import cache as C  # noqa: E402
from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.analyzer import analyze_full  # noqa: E402
from bunpo_analyzer.core.llm import LLMClient, LLMError  # noqa: E402
from bunpo_analyzer.core.llm.base import LLMResult  # noqa: E402
from tests.test_assemble import kho  # noqa: E402,F401  (fixture kho nho)


class Script:
    name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def generate(self, messages, output_model, model, timeout_s, max_tokens):
        self.calls.append((model, output_model.__name__, messages))
        if not self.script:
            raise AssertionError("khong duoc goi LLM")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(data=output_model.model_validate(item), model=model, prompt_tokens=10,
                         completion_tokens=5, cost_usd=0.001, latency_ms=100)


def _settings(**kw):
    base = dict(_env_file=None, openai_api_key="k", llm_model="main", llm_fallback_model="fb",
                llm_light_model="light", llm_max_retries=0)
    base.update(kw)
    return Settings(**base)


GOOD = P.fewshot_outputs()[0]  # EX1, vi tri theo cum
ERR = P.fewshot_outputs()[1]  # EX2: cau sai


def _en(ids=("g1", "r1", "r2", "r3", "r4", "r5", "r6")):
    return {"translation": "The cake I made with my sister last week was very tasty.",
            "glosses": [{"id": i, "gloss": f"EN {i}"} for i in ids],
            "reason": None, "explain": None, "word_meanings": []}


async def _run(kho, cache, script, lang="vi", text=P.EX1_TEXT, **kw):
    s = _settings(**kw)
    prov = Script(script)
    a = await analyze_full(text, lang, settings=s, kho=kho, cache=cache, client=LLMClient(prov, s, retry_delay_s=0))
    return a, prov


async def test_miss_then_hit(kho):
    cache = C.MemoryCache()
    a1, p1 = await _run(kho, cache, [GOOD])
    assert a1.cache == "miss" and len(p1.calls) == 1 and len(cache) == 2  # s + t:vi
    a2, p2 = await _run(kho, cache, [])
    assert a2.cache == "hit" and not p2.calls and a2.cost_usd == 0
    r1, r2 = a1.result.model_dump(), a2.result.model_dump()
    assert r1["id"] != r2["id"]
    r1.pop("id"), r2.pop("id")
    assert r1 == r2


async def test_light_translation(kho):
    cache = C.MemoryCache()
    a_vi, _ = await _run(kho, cache, [GOOD])
    a_en, prov = await _run(kho, cache, [_en()], lang="en")
    assert a_en.cache == "light"
    model, out_name, msgs = prov.calls[0]
    assert model == "light" and out_name == "LLMTextOutput"
    assert "TARGET language: English" in msgs[-1].content and "r3 | complement | 姉と |" in msgs[-1].content
    r = a_en.result
    assert r.translation.startswith("The cake") and {n.gloss for n in r.nodes} == {f"EN {n.id}" for n in r.nodes}
    # cau truc giu nguyen
    strip = lambda res: [(n.id, n.span, n.role, n.kind, n.grammar, n.parent) for n in res.nodes]  # noqa: E731
    assert strip(r) == strip(a_vi.result) and [g.id for g in r.grammar] == [g.id for g in a_vi.result.grammar]
    # lan sau tieng Anh: lay ngay
    a3, p3 = await _run(kho, cache, [], lang="en")
    assert a3.cache == "hit" and not p3.calls and a3.result.translation == r.translation


async def test_light_broken_falls_back_to_full(kho):
    cache = C.MemoryCache()
    await _run(kho, cache, [GOOD])
    bad = _en(ids=("r1",))  # thieu gloss, 2 model deu sai -> phan tich lai
    a, prov = await _run(kho, cache, [bad, bad, GOOD], lang="en")
    assert a.cache == "miss" and [c[1] for c in prov.calls] == ["LLMTextOutput", "LLMTextOutput", "LLMOutput"]
    assert [c[0] for c in prov.calls] == ["light", "fb", "main"]
    assert len(a.stage.attempts) == 3 and a.cost_usd == pytest.approx(0.003)
    assert a.result.error is None


async def test_grammar_error_light(kho):
    cache = C.MemoryCache()
    a_vi, _ = await _run(kho, cache, [ERR], text=P.EX2_TEXT)
    assert a_vi.result.error.code == "grammar_error"
    tr = {"translation": None, "glosses": [], "reason": None,
          "explain": "Past of an i-adjective: 寒い → 寒かった.", "word_meanings": []}
    a_en, _ = await _run(kho, cache, [tr], lang="en", text=P.EX2_TEXT)
    ic = a_en.result.input_check
    assert a_en.cache == "light" and ic.status == "error" and ic.explain.startswith("Past")
    assert ic.correction == a_vi.result.input_check.correction and ic.correction_at == a_vi.result.input_check.correction_at


async def test_failures_not_cached(kho):
    cache = C.MemoryCache()
    a, _ = await _run(kho, cache, [LLMError("timeout", "t"), LLMError("timeout", "t")])
    assert a.result.error.code == "llm_unavailable" and len(cache) == 0
    a, prov = await _run(kho, cache, [GOOD])
    assert a.cache == "miss" and len(prov.calls) == 1


async def test_key_includes_model_and_kho(kho):
    cache = C.MemoryCache()
    await _run(kho, cache, [GOOD])
    a, prov = await _run(kho, cache, [GOOD], llm_model="other")  # doi model -> khoa moi
    assert a.cache == "miss" and len(prov.calls) == 1
    k1 = C.base_key("x", "v1", "m")
    assert k1 != C.base_key("x", "v2", "m") and k1 != C.base_key("y", "v1", "m") and k1 == C.base_key("x", "v1", "m")


async def test_hit_without_llm_config(kho):
    cache = C.MemoryCache()
    await _run(kho, cache, [GOOD])
    s = _settings(llm_provider="nope")
    a = await analyze_full(P.EX1_TEXT, "vi", settings=s, kho=kho, cache=cache)
    assert a.cache == "hit" and a.result.error is None


async def test_struct_same_lang_is_hit(kho):
    cache = C.MemoryCache()
    await _run(kho, cache, [GOOD])
    for k in [k for k in cache._d if ":t:" in k]:
        del cache._d[k]  # ban theo ngon ngu het han, ban cau truc con
    a, prov = await _run(kho, cache, [])
    assert a.cache == "hit" and not prov.calls


async def test_broken_store_does_not_break(kho):
    class Broken:
        async def get(self, key):
            raise ConnectionError("redis down")

        async def set(self, key, value, ttl_s):
            raise ConnectionError("redis down")

    a, _ = await _run(kho, Broken(), [GOOD])
    assert a.result.error is None and a.cache == "miss"


async def test_corrupt_entry_ignored(kho):
    cache = C.MemoryCache()
    await _run(kho, cache, [GOOD])
    for k in list(cache._d):
        await cache.set(k, '{"status": "ok", "lang": "vi", "output": {"bad": 1}}', 60)
    a, prov = await _run(kho, cache, [GOOD])
    assert a.cache == "miss" and len(prov.calls) == 1


async def test_memory_lru_ttl():
    m = C.MemoryCache(max_items=2)
    await m.set("a", "1", 60)
    await m.set("b", "2", 60)
    assert await m.get("a") == "1"  # a moi dung -> b bi day ra
    await m.set("c", "3", 60)
    assert await m.get("b") is None and await m.get("a") == "1"
    await m.set("d", "4", 1)
    m._d["d"] = (0, "4")  # het han
    assert await m.get("d") is None


def test_get_cache_backends():
    assert isinstance(C.get_cache(_settings(cache_backend="none")), C.NoCache)
    m = C.get_cache(_settings(cache_backend="memory", cache_max_items=7))
    assert isinstance(m, C.MemoryCache) and m is C.get_cache(_settings(cache_backend="memory", cache_max_items=7))
    with pytest.raises(ValueError):
        C.get_cache(_settings(cache_backend="xx"))


def test_light_messages_hidden_and_group(kho):
    from bunpo_analyzer.core import translate as TR
    from bunpo_analyzer.core.llm_output import LLMOutput
    from bunpo_analyzer.core.tokenizer import tokenize

    toks = tokenize(P.EX1_TEXT)
    out = LLMOutput.model_validate(copy.deepcopy(P.EX1_OUT))
    msg = TR.build_messages(P.EX1_TEXT, toks, out, "vi", "en", ["料理"])[-1].content
    assert "g1 | relative clause | 先週姉と作った |" in msg and "r1 | hidden subject | （私が） | tôi" in msg
    assert "need meaning: 料理" in msg


async def test_light_copied_japanese_retried_with_fallback(kho):
    cache = C.MemoryCache()
    await _run(kho, cache, [GOOD])
    copied = _en()
    copied["translation"] = P.EX1_TEXT  # chep nguyen cau tieng Nhat (lan chay that 30/10)
    copied["glosses"] = [{"id": g["id"], "gloss": "先週姉と作った"} for g in copied["glosses"]]
    a, prov = await _run(kho, cache, [copied, _en()], lang="en")
    assert a.cache == "light" and [c[0] for c in prov.calls] == ["light", "fb"]
    assert "Problems:" in prov.calls[1][2][-1].content and a.result.translation.startswith("The cake")


def test_wrong_lang_checks():
    from bunpo_analyzer.core.translate import jp_ratio

    assert jp_ratio("昨日友達と見た映画", "en") == 1.0
    assert jp_ratio("我昨天和朋友看的电影", "cn") == 0.0  # chu Han la tieng Trung
    assert jp_ratio("い형용사는 과거형을 かった로 만듭니다 (面白い → 面白かった)", "ko") < 0.5


async def test_grammar_error_explain_copied_rejected(kho):
    cache = C.MemoryCache()
    a_vi, _ = await _run(kho, cache, [ERR], text=P.EX2_TEXT)
    same = {"translation": None, "glosses": [], "reason": None,
            "explain": a_vi.result.input_check.explain, "word_meanings": []}  # chep ban tieng Viet
    good = dict(same, explain="Past of an i-adjective: 寒い → 寒かった.")
    a, prov = await _run(kho, cache, [same, good], lang="en", text=P.EX2_TEXT)
    assert a.cache == "light" and a.result.input_check.explain.startswith("Past") and len(prov.calls) == 2
