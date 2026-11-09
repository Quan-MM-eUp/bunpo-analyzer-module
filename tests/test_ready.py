"""G3: check_ready - kiem tra cau hinh khi khoi dong (khong goi mang)."""

import asyncio
import json

import pytest

pytest.importorskip("sudachipy")

from bunpo_analyzer import check_ready  # noqa: E402
from bunpo_analyzer.config import Settings  # noqa: E402


def _kho(tmp_path):
    for p, obj in (("word/word_lib.json", []), ("grammar/grammar_lib.json", [{"id": 1, "grammar": "～は", "level": "N5"}]),
                   ("grammar/grammar_text.en.json", {"1": {"meaning": "topic"}})):
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _s(tmp_path, **kw):
    base = dict(_env_file=None, data_dir=_kho(tmp_path), openai_api_key="k", dict_provider="kho", cache_backend="memory")
    return Settings(**{**base, **kw})


def test_ready_ok(tmp_path):
    r = asyncio.run(check_ready(_s(tmp_path)))
    assert r["ok"] and set(r["checks"]) == {"kho", "tokenizer", "llm", "cache", "dictionary"}
    assert r["checks"]["kho"]["langs"] == ["en", "vi"]


def test_ready_missing(tmp_path):
    r = asyncio.run(check_ready(_s(tmp_path, openai_api_key="", data_dir=tmp_path / "khong_co")))
    assert not r["ok"] and not r["checks"]["llm"]["ok"] and not r["checks"]["kho"]["ok"]
    assert "k" not in r["checks"]["llm"]["detail"].split()  # khong in key


def test_ready_mazii_without_pem_is_warning(tmp_path):
    r = asyncio.run(check_ready(_s(tmp_path, dict_provider="mazii", mazii_pem_path=tmp_path / "x.pem")))
    assert r["ok"] and r["checks"]["dictionary"].get("warn")
    pem = tmp_path / "p.pem"
    pem.write_text("-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----\n", encoding="utf-8")
    r = asyncio.run(check_ready(_s(tmp_path, dict_provider="mazii", mazii_pem_path=pem)))
    assert r["ok"] and not r["checks"]["dictionary"].get("warn") and "abc" not in json.dumps(r)
