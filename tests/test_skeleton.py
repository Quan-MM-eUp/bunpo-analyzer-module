"""Buoc 0.1: kiem tra khung package."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import bunpo_analyzer
from bunpo_analyzer import SCHEMA_VERSION, AnalysisResult, Settings, analyze
from bunpo_analyzer.config import SUPPORTED_LANGS

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_version():
    assert bunpo_analyzer.__version__ == "0.1.0"
    assert SCHEMA_VERSION == "1.3"


def test_settings_defaults(monkeypatch):
    for k in ("BUNPO_LLM_PROVIDER", "BUNPO_MAX_CHARS", "BUNPO_DEFAULT_LANG"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_provider == "gemini"
    assert s.max_chars == 100
    assert s.default_lang == "vi"


def test_settings_env_override(monkeypatch):
    # Doi model chi can doi bien moi truong.
    monkeypatch.setenv("BUNPO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("BUNPO_LLM_MODEL", "qwen3.8-flash")
    s = Settings(_env_file=None)
    assert (s.llm_provider, s.llm_model) == ("qwen", "qwen3.8-flash")


def test_supported_langs():
    assert len(SUPPORTED_LANGS) == 16 and len(set(SUPPORTED_LANGS)) == 16


async def test_analyze_not_implemented():
    with pytest.raises(NotImplementedError):
        await analyze("今夜たくさんの宿題がある。")


def test_schema_example_ok():
    r = AnalysisResult.model_validate(load("result_ok.json"))
    assert r.error is None and r.input_check.status == "ok"
    assert [n.id for n in r.nodes if n.main] == ["r6"]
    assert {t.surface: t.pos_sub for t in r.tokens if t.pos_sub} == {"見": "v2", "面白かっ": "adj_i"}
    # Vong lai JSON khong mat du lieu.
    again = AnalysisResult.model_validate_json(r.model_dump_json())
    assert again == r


def test_schema_example_grammar_error():
    r = AnalysisResult.model_validate(load("result_grammar_error.json"))
    assert r.error.code == "grammar_error"
    assert r.input_check.correction == "映画は面白かったです。"


def test_schema_rejects_bad_node():
    data = load("result_ok.json")
    del data["nodes"][2]["role"]
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


def test_schema_rejects_unknown_parent():
    data = load("result_ok.json")
    data["nodes"][1]["parent"] = "g9"
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


def test_schema_rejects_unknown_field():
    data = load("result_ok.json")
    data["subtitle"] = "x"
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


def test_schema_rejects_unknown_pos_sub():
    data = load("result_ok.json")
    data["tokens"][0]["pos_sub"] = "v4"
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)
