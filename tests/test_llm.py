"""Buoc 2.1: lop goi LLM (khong goi mang; test that danh dau `live`)."""

import os
from types import SimpleNamespace
from typing import Optional

import openai

try:  # openai 3.x dung httpx2, openai 2.x dung httpx
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx
import pytest
from pydantic import BaseModel

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.llm import LLMClient, LLMError, Message
from bunpo_analyzer.core.llm.base import LLMResult
from bunpo_analyzer.core.llm.openai_compat import OpenAICompatProvider, strict_schema

REQ = httpx.Request("POST", "https://llm-api.eup.ai/v1/chat/completions")
MSGS = [Message("user", "今夜たくさんの宿題がある。")]


class Out(BaseModel):
    translation: str
    note: Optional[str] = None


def _resp(content: str, finish: str = "stop", model: str = "gpt-4.1-mini"):
    msg = SimpleNamespace(content=content, refusal=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)], model=model,
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


def _status(cls, code: int, msg: str = "x"):
    return cls(msg, response=httpx.Response(code, request=REQ), body=None)


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _provider(script):
    comp = FakeCompletions(script)
    client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return OpenAICompatProvider("k", prices={"gpt-4.1-mini": (0.4, 1.6)}, client=client), comp


def _settings(**kw):
    base = dict(llm_model="gpt-4.1-mini", llm_fallback_model="gpt-4.1", llm_max_retries=1,
                openai_api_key="k", _env_file=None)
    base.update(kw)
    return Settings(**base)


async def test_ok_json_schema_and_cost():
    p, comp = _provider([_resp('{"translation": "Tối nay có nhiều bài tập.", "note": null}')])
    r = await p.generate(MSGS, Out, "gpt-4.1-mini", 10, 500)
    assert r.data.translation.startswith("Tối nay") and r.mode == "json_schema"
    assert (r.prompt_tokens, r.completion_tokens) == (100, 20)
    assert r.cost_usd == pytest.approx((100 * 0.4 + 20 * 1.6) / 1e6)
    rf = comp.calls[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert comp.calls[0]["temperature"] == 0


async def test_reasoning_model_params():
    p, comp = _provider([_resp('{"translation": "x", "note": null}')])
    await p.generate(MSGS, Out, "gpt-5-mini", 10, 500)
    kw = comp.calls[0]
    assert "temperature" not in kw and kw["max_completion_tokens"] == 2000 and kw["reasoning_effort"] == "low"
    p, comp = _provider([_resp('{"translation": "x", "note": null}')])
    await p.generate(MSGS, Out, "gpt-4.1-mini", 10, 500)
    assert comp.calls[0]["temperature"] == 0 and comp.calls[0]["max_tokens"] == 500


def test_cached_cost():
    from bunpo_analyzer.core.llm.base import estimate_cost

    prices = {"gpt-4.1": (2.0, 8.0)}
    assert estimate_cost(prices, "gpt-4.1", 1000, 100) == pytest.approx((2000 + 800) / 1e6)
    assert estimate_cost(prices, "gpt-4.1", 1000, 100, cached=800) == pytest.approx((200 * 2 + 800 * 0.5 + 800) / 1e6)


def test_strict_schema_requires_all_fields():
    s = strict_schema(Out)
    assert set(s["required"]) == {"translation", "note"} and s["additionalProperties"] is False


async def test_fallback_to_json_object_when_schema_unsupported():
    p, comp = _provider([_status(openai.BadRequestError, 400, "response_format json_schema not supported"),
                         _resp('{"translation": "x", "note": null}')])
    r = await p.generate(MSGS, Out, "m", 10, 500)
    assert r.mode == "json_object" and comp.calls[1]["response_format"] == {"type": "json_object"}
    assert "schema" in comp.calls[1]["messages"][-1]["content"]


@pytest.mark.parametrize("exc,kind", [
    (openai.APITimeoutError(request=REQ), "timeout"),
    (_status(openai.RateLimitError, 429), "unavailable"),
    (_status(openai.RateLimitError, 429, "môi trường dev đã hết ngân sách tổng của tháng"), "quota"),
    (_status(openai.InternalServerError, 502), "unavailable"),
    (_status(openai.AuthenticationError, 401), "config"),
    (_status(openai.NotFoundError, 404), "config"),
    (_status(openai.BadRequestError, 400, "invalid model"), "config"),
])
async def test_error_mapping(exc, kind):
    p, _ = _provider([exc])
    with pytest.raises(LLMError) as ei:
        await p.generate(MSGS, Out, "m", 10, 500)
    assert ei.value.kind == kind


@pytest.mark.parametrize("resp", [_resp('{"wrong": 1}'), _resp('{"translation": "x"', finish="length"), _resp("")])
async def test_bad_output(resp):
    p, _ = _provider([resp])
    with pytest.raises(LLMError) as ei:
        await p.generate(MSGS, Out, "m", 10, 500)
    assert ei.value.kind == "bad_output"


def test_missing_key():
    with pytest.raises(LLMError) as ei:
        OpenAICompatProvider("")
    assert ei.value.kind == "config"


class ScriptProvider:
    """Gia lap nha cung cap: tra theo kich ban cho tung model."""

    name = "fake"

    def __init__(self, script: dict):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []

    async def generate(self, messages, output_model, model, timeout_s, max_tokens):
        self.calls.append(model)
        item = self.script[model].pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(data=output_model(translation=item), model=model)


async def test_client_retry_then_ok():
    p = ScriptProvider({"gpt-4.1-mini": [LLMError("timeout", "t"), "ok"]})
    r = await LLMClient(p, _settings(), retry_delay_s=0).generate(MSGS, Out)
    assert r.data.translation == "ok" and r.attempts == 2 and not r.used_fallback


async def test_client_fallback_after_retries():
    p = ScriptProvider({"gpt-4.1-mini": [LLMError("unavailable", "u")] * 2, "gpt-4.1": ["fb"]})
    r = await LLMClient(p, _settings(), retry_delay_s=0).generate(MSGS, Out)
    assert r.used_fallback and r.model == "gpt-4.1" and p.calls == ["gpt-4.1-mini", "gpt-4.1-mini", "gpt-4.1"]


async def test_client_bad_output_not_retried_but_fallback():
    p = ScriptProvider({"gpt-4.1-mini": [LLMError("bad_output", "b")], "gpt-4.1": ["fb"]})
    r = await LLMClient(p, _settings(), retry_delay_s=0).generate(MSGS, Out)
    assert p.calls == ["gpt-4.1-mini", "gpt-4.1"] and r.used_fallback


async def test_client_use_fallback_directly():
    p = ScriptProvider({"gpt-4.1": ["fb"]})
    r = await LLMClient(p, _settings(), retry_delay_s=0).generate(MSGS, Out, use_fallback=True)
    assert p.calls == ["gpt-4.1"] and r.used_fallback


async def test_client_all_fail():
    p = ScriptProvider({"gpt-4.1-mini": [LLMError("timeout", "t")] * 2, "gpt-4.1": [LLMError("timeout", "t")] * 2})
    with pytest.raises(LLMError) as ei:
        await LLMClient(p, _settings(), retry_delay_s=0).generate(MSGS, Out)
    assert ei.value.kind == "timeout" and len(p.calls) == 4


async def test_client_bad_key_no_fallback():
    p = ScriptProvider({"gpt-4.1-mini": [LLMError("config", "sai key")], "gpt-4.1": ["fb"]})
    with pytest.raises(LLMError):
        await LLMClient(p, _settings(), retry_delay_s=0).generate(MSGS, Out)
    assert p.calls == ["gpt-4.1-mini"]


def test_settings_defaults(monkeypatch):
    for k in list(os.environ):
        if k.startswith("BUNPO_"):
            monkeypatch.delenv(k)
    s = Settings(_env_file=None)
    assert (s.llm_provider, s.llm_model, s.llm_fallback_model) == ("openai", "gpt-5-mini", "gpt-4.1")
    assert s.openai_base_url == "https://llm-api.eup.ai/v1"


@pytest.mark.live
async def test_live_call():
    """Goi that: pytest -m live (can .env co BUNPO_OPENAI_API_KEY va mang toi gateway)."""
    s = Settings()
    if not s.openai_api_key:
        pytest.skip("chua co BUNPO_OPENAI_API_KEY")
    r = await LLMClient(settings=s).generate(
        [Message("system", "Dich cau tieng Nhat sang tieng Viet. note = null."), *MSGS], Out)
    assert r.data.translation and r.prompt_tokens > 0


async def test_quota_not_retried_no_fallback():
    s = _settings(llm_max_retries=2, llm_fallback_model="fb")
    prov = ScriptProvider({"gpt-4.1-mini": [LLMError("quota", "het ngan sach")], "fb": ["never"]})
    c = LLMClient(prov, s, retry_delay_s=0)
    with pytest.raises(LLMError) as e:
        await c.generate([], Out)
    assert e.value.kind == "quota" and len(prov.calls) == 1
