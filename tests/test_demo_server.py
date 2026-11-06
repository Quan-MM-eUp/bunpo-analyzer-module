"""Trang test tren may (scripts/demo_server.py): API voi LLM gia."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sudachipy")
from fastapi.testclient import TestClient  # noqa: E402

from bunpo_analyzer.config import Settings  # noqa: E402
from bunpo_analyzer.core import prompt as P  # noqa: E402
from bunpo_analyzer.core.llm import LLMClient  # noqa: E402
from tests.test_assemble import kho  # noqa: E402,F401
from tests.test_cache import Script  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _app(kho, script):
    spec = importlib.util.spec_from_file_location("demo_server", ROOT / "scripts" / "demo_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    s = Settings(_env_file=None, openai_api_key="k", llm_model="main", llm_fallback_model="fb", llm_max_retries=0)
    prov = Script(script)
    return TestClient(mod.create_app(s, kho, LLMClient(prov, s, retry_delay_s=0))), prov


def test_page_and_health(kho):
    c, _ = _app(kho, [])
    r = c.get("/")
    assert r.status_code == 200 and "<!doctype html>" in r.text and "/*MOCK*/null" in r.text
    h = c.get("/api/health").json()
    assert h["ok"] and h["model"] == "main" and h["has_key"]


def test_analyze_cache_and_errors(kho):
    c, prov = _app(kho, [P.fewshot_outputs()[0]])
    r = c.post("/api/analyze", json={"text": P.EX1_TEXT, "lang": "vi"}).json()
    assert r["result"]["translation"] and r["meta"]["cache"] == "miss" and r["meta"]["models"] == ["main"]
    r2 = c.post("/api/analyze", json={"text": P.EX1_TEXT, "lang": "vi"}).json()  # lan 2: cache, khong goi LLM
    assert r2["meta"]["cache"] == "hit" and len(prov.calls) == 1
    bad = c.post("/api/analyze", json={"text": "hello", "lang": "vi"}).json()
    assert bad["result"]["error"]["code"] == "invalid_input"
    assert c.post("/api/analyze", json={"text": "x", "lang": "xx"}).status_code == 400


def test_grammar(kho):
    c, _ = _app(kho, [])
    g = c.get("/api/grammar/19?lang=vi").json()
    assert g["id"] == 19 and g["short_label"] == "と"
    assert c.get("/api/grammar/999999").status_code == 404
