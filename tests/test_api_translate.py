"""api_translate.py voi client gia (khong goi mang, khong ton tien)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "translation"
sys.path.insert(0, str(TOOLS))

import api_translate as at
import common
import tm

from tests.test_translation_tools import GOOD_EN, SRC_ITEMS


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """Tra loi theo loai yeu cau: dich -> GOOD_EN; cham -> issues theo self.issues; sua -> self.fixes."""

    def __init__(self, translations=None, issues=None, fixes=None, cut_first=False):
        self.translations = translations or GOOD_EN
        self.issues = issues or {}          # {id: [issue, ...]} cho lan cham dau
        self.fixes = fixes or {}            # {id: {field: value}}
        self.cut_first = cut_first
        self.calls = []
        self.messages = SimpleNamespace(stream=self.stream)

    def stream(self, model, max_tokens, system, messages):
        user = messages[0]["content"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        kind = "dich" if user.startswith("Translate") else "cham" if user.startswith("Review") else "sua"
        self.calls.append((kind, model))
        ids = [int(x) for x in re.findall(r'"id": (\d+)', user)]
        stop = "end_turn"
        if kind == "dich":
            if self.cut_first and len(ids) > 1:
                self.cut_first = False
                text, stop = '{"items": [', "max_tokens"
            else:
                text = json.dumps({"items": [{"id": i, "fields": self.translations[i]} for i in ids]}, ensure_ascii=False)
        elif kind == "cham":
            first = sum(1 for k, _ in self.calls if k == "cham") == 1
            text = "```json\n" + json.dumps({"items": [{"id": i, "issues": (self.issues.get(i, []) if first else [])}
                                                       for i in ids], "summary": "ok"}) + "\n```"
        else:
            text = json.dumps({"items": [{"id": i, "fields": self.fixes.get(i, {})} for i in ids]}, ensure_ascii=False)
        u = SimpleNamespace(input_tokens=1000, output_tokens=500, cache_creation_input_tokens=0, cache_read_input_tokens=2000)
        return FakeStream(SimpleNamespace(usage=u, stop_reason=stop, content=[SimpleNamespace(type="text", text=text)]))


@pytest.fixture
def ws(tmp_path):
    w = tmp_path / "translation"
    common.write_json(w / "source" / "b001.json", {"batch": "b001", "items": SRC_ITEMS})
    common.write_json(w / "source" / "index.json", {"kho_version": "x", "batches": [
        {"batch": "b001", "items": 2, "chars": 100, "levels": ["N5"], "ids": [1618, 7], "hash": "h1"}]})
    common.write_json(w / "glossary" / "en.json", {"terms": [
        {"id": "noun", "vi": ["danh từ"], "ja": "名詞", "tr": "noun", "accept": [], "note": "", "check": True}]})
    common.write_text(w / "style" / "en.md", "# English style\nTextbook register.\n")
    tm.init_manifests(w, ["en"])
    return w


def _args(ws, *extra):
    return at.build_parser().parse_args(["en", "--ws", str(ws), *extra])


def test_run_updates_manifest_and_releases_lock(ws):
    fake = FakeClient()
    assert at.run(_args(ws, "--n", "5"), client=fake) == 0
    rows = {r["batch"]: r for r in tm.load_manifest(ws, "en")}
    assert rows["b001"]["status"] == "passed" and rows["b001"]["score"] == "100.0"
    assert tm.lock_holder(ws, "en") is None
    out = common.read_json(ws / "out" / "en" / "b001.json")
    assert out["prompt_ver"] == at.PROMPT_VER and all(i["qa"]["qa"] == "ok" for i in out["items"])
    usage = (ws / "reports" / "en" / "api_usage.csv").read_text(encoding="utf-8").splitlines()
    assert usage[0].startswith("time,batch,stage") and len(usage) == 1 + len(fake.calls)
    assert [k for k, _ in fake.calls] == ["dich", "cham"]
    assert fake.calls[0][1] == at.MODEL_T and fake.calls[1][1] == at.MODEL_J
    rep = sorted((ws / "reports" / "en").glob("api-*.json"))
    assert rep and common.read_json(rep[-1])["usd"] > 0


def test_pilot_does_not_touch_real_workspace(ws, tmp_path):
    before = (ws / "manifest" / "en.csv").read_text(encoding="utf-8")
    pilot = tmp_path / "pilot_api"
    assert at.run(_args(ws, "--batches", "b001", "--pilot", str(pilot)), client=FakeClient()) == 0
    assert (ws / "manifest" / "en.csv").read_text(encoding="utf-8") == before
    assert not (ws / "out").exists() and not (ws / "locks" / "en.lock").exists()
    assert (pilot / "out" / "en" / "b001.json").exists() and (pilot / "reports" / "en" / "api_usage.csv").exists()


def test_busy_lock(ws):
    tm.claim(ws, "en", "cowork-en")
    assert at.run(_args(ws), client=FakeClient()) == 2
    assert tm.lock_holder(ws, "en") == "cowork-en"


def test_cut_output_is_split(ws):
    fake = FakeClient(cut_first=True)
    assert at.run(_args(ws, "--chunk-chars", "100000"), client=fake) == 0
    assert [k for k, _ in fake.calls][:3] == ["dich", "dich", "dich"]  # 1 lan bi cat + 2 nua
    assert tm.load_manifest(ws, "en")[0]["status"] == "passed"


def test_checker_error_is_repaired(ws):
    bad = json.loads(json.dumps(GOOD_EN))
    bad = {int(k): v for k, v in bad.items()}
    bad[7]["meaning"] = "Uses te kara to state the order"  # mat chu Nhat 〜てから
    fake = FakeClient(translations=bad, fixes={7: {"meaning": GOOD_EN[7]["meaning"]}})
    assert at.run(_args(ws), client=fake) == 0
    assert [k for k, _ in fake.calls] == ["dich", "sua", "cham"]
    out = {i["id"]: i for i in common.read_json(ws / "out" / "en" / "b001.json")["items"]}
    assert out[7]["fields"]["meaning"] == GOOD_EN[7]["meaning"]


def test_major_issue_fixed_then_rejudged(ws):
    issue = {"field": "meaning", "category": "accuracy", "severity": "major", "note": "x", "fix": "Expresses continuity"}
    fake = FakeClient(issues={1618: [issue]}, fixes={1618: {"meaning": "Expresses continuity"}})
    assert at.run(_args(ws), client=fake) == 0
    assert [k for k, _ in fake.calls] == ["dich", "cham", "sua", "cham"]
    out = {i["id"]: i for i in common.read_json(ws / "out" / "en" / "b001.json")["items"]}
    assert out[1618]["fields"]["meaning"] == "Expresses continuity" and out[1618]["qa"]["qa"] == "ok"


def test_unfixed_major_issue_becomes_qa_low(ws):
    issue = {"field": "meaning", "category": "accuracy", "severity": "major", "note": "x"}

    class Stubborn(FakeClient):  # cham lai van bao loi
        def stream(self, model, max_tokens, system, messages):
            s = super().stream(model, max_tokens, system, messages)
            if messages[0]["content"].startswith("Review"):
                ids = [int(x) for x in re.findall(r'"id": (\d+)', messages[0]["content"])]
                s.msg.content[0].text = json.dumps({"items": [{"id": i, "issues": [issue] if i == 1618 else []}
                                                              for i in ids], "summary": ""})
            return s

    fake = Stubborn()
    assert at.run(_args(ws), client=fake) == 0
    assert [k for k, _ in fake.calls] == ["dich", "cham", "sua", "cham", "sua", "cham"]
    row = tm.load_manifest(ws, "en")[0]
    assert row["status"] == "qa_low" and row["qa_low"] == "1"


def test_budget_stop(ws):
    fake = FakeClient()
    assert at.run(_args(ws, "--max-usd", "0.000001"), client=fake) == 3
    assert len(fake.calls) == 1
    assert tm.load_manifest(ws, "en")[0]["status"] == "pending"  # lo do dang khong bi danh dau
    assert tm.lock_holder(ws, "en") is None


def test_low_resource_adds_backtranslation_judge(ws):
    common.write_json(ws / "glossary" / "my.json", {"terms": []})
    common.write_text(ws / "style" / "my.md", "Burmese style")
    fake = FakeClient(issues={7: [{"field": "meaning", "category": "accuracy", "severity": "minor", "note": "x"}]})
    job = at.BatchJob(ws, "my", "b001", at.Claude(fake, at.Usage(None, None)), at.MODEL_T, at.MODEL_J, 7000, "d")
    j = job.judge({})
    assert [m for _, m in fake.calls] == [at.MODEL_J, at.MODEL_T]  # Sonnet cham + Opus dich nguoc
    assert j[7]["score"] == 99 and j[7]["qa"] == "ok" and j[1618]["score"] == 100


def test_parse_json_and_key(tmp_path, monkeypatch, capsys):
    assert at.parse_json('noise ```json\n{"items": []}\n``` tail') == {"items": []}
    assert at.parse_json('Here: {"a": 1} trailing') == {"a": 1}
    with pytest.raises(ValueError):
        at.parse_json("no json")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('BUNPO_DATA_DIR=..\nANTHROPIC_API_KEY="sk-test-123"\n', encoding="utf-8")
    assert at.load_key(env) == "sk-test-123"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert at.load_key(env) == "sk-env"
    assert "sk-" not in capsys.readouterr().out


def test_chunks_and_system_prompt(ws):
    items = [{"id": i, "fields": {"meaning": {"text": "x" * 3000}}} for i in range(5)]
    assert [len(c) for c in at.chunks(items, 7000)] == [2, 2, 1]
    s = at.system_translate(ws, "en")
    assert "danh từ (名詞) → noun" in s and "Textbook register" in s and '"items"' in s
