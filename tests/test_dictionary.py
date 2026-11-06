"""Tu dien Mazii: giai ma, client (khong goi mang that), chon muc tu / nghia, tich hop vao phan tich."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path

import httpx
import pytest

pytest.importorskip("sudachipy")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import padding  # noqa: E402
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: E402

from bunpo_analyzer.core import cache as C  # noqa: E402
from bunpo_analyzer.core.dictionary import mazii as M  # noqa: E402
from bunpo_analyzer.core.dictionary.base import DictEntry, Sense  # noqa: E402
from bunpo_analyzer.core.lookup import apply_to_tokens, entry_meaning, lookup_dict, pick_entry  # noqa: E402
from bunpo_analyzer.core.tokenizer import tokenize  # noqa: E402
from tests.test_assemble import kho  # noqa: E402,F401  (fixture kho nho)

FIX = Path(__file__).parent / "fixtures" / "mazii"
PEM = "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEtest\nkey==\n-----END PUBLIC KEY-----\n"


def encrypt(obj, pem: str = PEM, iv: bytes = b"0123456789abcdef") -> str:
    key = M.derive_key(pem)
    p = padding.PKCS7(128).padder()
    data = p.update(json.dumps(obj, ensure_ascii=False).encode()) + p.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    return base64.b64encode(iv).decode() + ":" + base64.b64encode(ct).decode()


def neko() -> dict:
    return json.loads((FIX / "jaen_neko.json").read_text(encoding="utf-8"))


# ---------------- giai ma + doc ket qua ----------------
def test_key_ignores_newlines():
    assert M.derive_key(PEM) == M.derive_key(PEM.replace("\n", "\r\n") + "  ")
    assert len(M.derive_key(PEM)) == 32


def test_decrypt_roundtrip_and_parse_real_sample():
    payload = neko()
    assert M.decrypt_payload(encrypt(payload), M.derive_key(PEM)) == payload
    (e,) = M.parse_words(payload)
    assert e.word == "猫" and e.readings == ("ねこ", "ねこま") and e.level == "N5" and e.han == "MIÊU"
    assert e.senses[0] == Sense("cat (esp. the domestic cat, Felis catus); feline", ("n",), ("ねこ",))
    assert e.senses[3].kinds == ("n", "abbr")
    assert DictEntry.from_json(e.to_json()) == e
    assert M.parse_words({"data": {"words": [{"word": ""}, "x", {"word": "a", "level": "N3"}]}})[0].level == "N3"
    assert M.parse_words(None) == []


# ---------------- client ----------------
def make_dict(handler, cache=None, **kw):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return M.MaziiDictionary(PEM, cache=cache, http=http, **kw)


async def test_client_posts_decrypts_and_caches():
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        return httpx.Response(200, json={"status": 200, "encryptedData": encrypt(neko())})

    cache = C.MemoryCache()
    d = make_dict(handler, cache=cache)
    r = await d.search_many(["猫", "猫", ""], "pl")
    assert list(r) == ["猫"] and r["猫"][0].word == "猫"
    assert seen == [{"dict": "jaen", "query": "猫", "limit": 3}]  # pl -> tu dien tieng Anh
    r2 = await d.search_many(["猫"], "pl")
    assert r2["猫"][0].senses == r["猫"][0].senses and len(seen) == 1 and d.stats["cache_hits"] == 1
    assert "bunpo:d:jaen:猫" in cache._d
    await d.search_many(["猫"], "tw")
    assert seen[-1]["dict"] == "jatw"


async def test_errors_not_cached_and_breaker():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    cache = C.MemoryCache()
    d = make_dict(handler, cache=cache)
    for i in range(M.BREAKER_FAILS):
        assert await d.search_many([f"w{i}"], "en") == {}
    assert len(cache) == 0 and d.stats["errors"] == M.BREAKER_FAILS
    assert await d.search_many(["x"], "en") == {} and len(calls) == M.BREAKER_FAILS  # dang ngung goi
    assert d.stats["skipped"] == 1


async def test_bad_payload_and_plain_json():
    d = make_dict(lambda req: httpx.Response(200, json={"encryptedData": "AAAA:BBBB"}))
    assert await d.search_many(["猫"], "en") == {}
    d2 = make_dict(lambda req: httpx.Response(200, json=neko()))  # x-no-encryption: JSON tho
    assert (await d2.search_many(["猫"], "en"))["猫"][0].word == "猫"


async def test_empty_result_cached_short():
    cache = C.MemoryCache()
    d = make_dict(lambda req: httpx.Response(200, json={"encryptedData": encrypt({"data": {"words": []}})}),
                  cache=cache)
    assert (await d.search_many(["zzz"], "en")) == {"zzz": []}
    exp, _ = cache._d["bunpo:d:jaen:zzz"]
    import time
    assert exp - time.time() <= M.EMPTY_TTL_S + 1


async def test_timeout_drops_slow_words():
    async def handler(req):
        if json.loads(req.content)["query"] == "slow":
            await asyncio.sleep(1)
        return httpx.Response(200, json={"encryptedData": encrypt(neko())})

    d = make_dict(handler, timeout_s=0.1)
    r = await d.search_many(["slow", "猫"], "en")
    assert list(r) == ["猫"]


def test_from_settings_requires_pem(tmp_path):
    from bunpo_analyzer.config import Settings

    s = Settings(_env_file=None, dict_provider="mazii", mazii_pem_path=tmp_path / "none.pem")
    with pytest.raises(OSError):
        M.MaziiDictionary.from_settings(s)
    (tmp_path / "p.pem").write_text(PEM, encoding="utf-8")
    d = M.MaziiDictionary.from_settings(s.model_copy(update={"mazii_pem_path": tmp_path / "p.pem"}))
    assert d._key == M.derive_key(PEM)
    with pytest.raises(ValueError):
        M.MaziiDictionary("  ")


# ---------------- chon muc tu / nghia ----------------
def E(word, readings, *senses, level=None, han=None, short=None, id="x"):
    return DictEntry(id=id, word=word, readings=tuple(readings), level=level, han=han, short_mean=short,
                     senses=tuple(Sense(m, tuple(k.split(", ")) if k else (), tuple(r)) for m, k, r in senses))


def test_pick_entry_rules():
    noru = E("乗る", ["のる"], ("ride", "v5r", []))
    nobo = E("登る", ["のぼる"], ("climb", "v5r", []))
    assert pick_entry([noru, nobo], ("登る", "登っ", "上る"), "verb", None) is nobo
    tsukeru = E("付ける", ["つける"], ("attach", "v1, vt", []))
    assert pick_entry([tsukeru], ("つける",), "verb", "つける") is tsukeru  # kana -> muc co chu Han cung cach doc
    te = E("手", ["て"], ("hand", "n", []), id="te")
    assert pick_entry([te], ("て",), "noun", "て") is None  # qua ngan, de trung am
    assert pick_entry([te], ("て",), "noun", "て", frozenset({"te"})) is te  # tru khi la ket qua dau cua chinh tu do
    other = E("別", ["べつ"], ("other", "n", []))
    assert pick_entry([other], ("猫",), "noun", "ねこ") is None  # khac chu, token co chu Han
    n_entry = E("見", ["み"], ("viewing", "n", []))
    v_entry = E("見る", ["みる"], ("to see", "v1", []))
    assert pick_entry([n_entry, v_entry], ("見る", "見"), "verb", None) is v_entry  # dung tu loai truoc


def test_entry_meaning():
    e = E("猫", ["ねこ", "ねこま"], ("cat; feline", "n", ["ねこ"]), ("shamisen", "n", ["ねこ"]),
          ("geisha", "n", ["ねこ"]), ("wheelbarrow", "n", ["ねこ"]), ("old cat", "n, arch", ["ねこま"]))
    assert entry_meaning(e, "noun", "ねこ") == "cat; feline; shamisen; geisha"
    assert entry_meaning(e, "noun", "ねこま") == "old cat"
    long = E("x", [], ("a" * 100, "n", []), ("b" * 30, "n", []))
    assert entry_meaning(long, "noun", None) == "a" * 100  # vuot 120 ky tu thi dung
    mixed = E("勉強", ["べんきょう"], ("study", "n, vs, vt", []), ("discount", "n, vs", []))
    assert entry_meaning(mixed, "noun", None) == "study; discount"
    verb_only = E("する", ["する"], ("to do", "vs-i", []), ("thing", "n", []))
    assert entry_meaning(verb_only, "verb", None) == "to do"
    vi_kind = E("猫", ["ねこ"], ("con mèo", "danh từ", []))  # tu loai khong theo JMdict: khong loc
    assert entry_meaning(vi_kind, "verb", None) == "con mèo"
    assert entry_meaning(E("x", [], short="a; " + "b" * 200), "noun", None) == "a"


class FakeDict:
    def __init__(self, data):
        self.data = data
        self.queries = []

    async def search_many(self, queries, lang):
        self.queries.append((list(queries), lang))
        return {q: self.data[q] for q in queries if q in self.data}


FUJI = {
    "富士山": [E("富士山", ["ふじさん"], ("Mount Fuji", "n", []), level="N3", han="PHÚ SĨ SƠN", id="fuji")],
    "登る": [E("登る", ["のぼる"], ("to climb; to go up", "v5r, vi", []), level="N4", id="noboru")],
    "こと": [E("事", ["こと"], ("thing; matter", "n", []), level="N5", id="koto")],
    "有る": [E("有る", ["ある"], ("to exist; to have", "v5r-i, vi", []), level="N5", id="aru")],
}


async def test_lookup_dict_fuji_sentence():
    toks = tokenize("富士山に登ったことがありますか。")
    d = FakeDict(FUJI)
    lk = await lookup_dict(toks, d, "en")
    m = {toks[w.i].surface: (w.meaning, w.meaning_source, w.level, w.dict_id) for w in lk.words}
    assert m["富士山"] == ("Mount Fuji", "dict", "N3", "fuji")
    assert m["登っ"][:2] == ("to climb; to go up", "dict")
    assert m["あり"][:2] == ("to exist; to have", "dict")
    assert m["に"][1] == m["た"][1] == m["が"][1] == "particle_table"
    assert m["こと"][:2] == ("thing; matter", "dict")  # kana ngan: nhan vi la ket qua dau tien cua "こと"
    assert m["。"][1] == "none"
    assert lk.misses == [] and lk.stats["answered"] >= 4
    (qs, lang), = d.queries
    assert lang == "en" and "富士山" in qs and "登る" in qs and "に" not in qs
    tokens = apply_to_tokens(toks, lk)
    assert tokens[0].level == "N3" and tokens[0].dict_id == "fuji" and tokens[0].han is None  # han chi cho vi
    vi = apply_to_tokens(toks, await lookup_dict(toks, FakeDict(FUJI), "vi"))
    assert vi[0].han == "PHÚ SĨ SƠN"
    assert tokens[1].level is None  # tro tu: khong co thong tin tu dien


async def test_lookup_dict_multi_parts_and_misses():
    data = {
        "気をつける": [E("気をつける", ["きをつける"], ("to be careful", "exp, v1", []), id="kiwo")],
        "子供": [E("子供", ["こども"], ("child", "n", []))],
        "猫": M.parse_words(neko()),
    }
    toks = tokenize("気をつけて走る。")
    lk = await lookup_dict(toks, FakeDict(data), "en")
    assert [w.via for w in lk.words[:3]] == ["multi"] * 3 and lk.words[0].meaning == "to be careful"
    assert lk.words[4].meaning_source == "llm" and lk.misses == ["走る"]  # tu dien khong tra duoc -> LLM
    toks = tokenize("子供たちが猫を見ている。")
    lk = await lookup_dict(toks, FakeDict(data), "en")
    assert lk.words[0].via == "parts" and lk.words[0].meaning.startswith("子供 (child) + たち (")
    assert lk.words[2].meaning.startswith("cat (esp. the domestic cat")


async def test_lookup_dict_all_failed_falls_back_to_llm():
    toks = tokenize("富士山に登った。")
    lk = await lookup_dict(toks, FakeDict({}), "en")
    assert [toks[w.i].surface for w in lk.words if w.meaning_source == "llm"] == ["富士山", "登っ"]
    assert lk.misses == ["富士山", "登る"]


# ---------------- tich hop analyze_full ----------------
async def test_analyze_full_uses_dictionary(kho):
    from bunpo_analyzer.core.analyzer import analyze_full
    from bunpo_analyzer.core.llm import LLMClient
    from tests.test_cache import GOOD, Script, _settings

    data = {"先週": [E("先週", ["せんしゅう"], ("last week", "n-adv, n-t", []), level="N5", id="senshu")]}
    s = _settings()
    prov = Script([GOOD])
    a = await analyze_full("先週姉と作ったケーキはとてもおいしかったです。", "vi", settings=s, kho=kho,
                           cache=C.MemoryCache(), client=LLMClient(prov, s, retry_delay_s=0), dictionary=FakeDict(data))
    t0 = a.result.tokens[0]
    assert t0.surface == "先週" and t0.meaning == "last week" and t0.meaning_source == "dict" and t0.level == "N5"
    assert a.log_dict()["dict"]["answered"] == 1
    # tu khong co trong tu dien -> LLM duoc nho dien nghia (need meaning) nhu cu
    user_msg = prov.calls[0][2][-1].content
    assert "作っ" in user_msg.split("need meaning:")[1]


async def test_provider_kho_by_default_and_bad_pem_falls_back(kho, tmp_path):
    from bunpo_analyzer.core.analyzer import get_dictionary
    from tests.test_cache import _settings

    assert get_dictionary(_settings()) is None
    assert get_dictionary(_settings(dict_provider="mazii", mazii_pem_path=tmp_path / "x.pem")) is None
    (tmp_path / "p.pem").write_text(PEM, encoding="utf-8")
    d = get_dictionary(_settings(dict_provider="mazii", mazii_pem_path=tmp_path / "p.pem"))
    assert isinstance(d, M.MaziiDictionary)


@pytest.mark.skipif(not os.environ.get("BUNPO_MAZII_LIVE"), reason="goi Mazii that: BUNPO_MAZII_LIVE=1")
@pytest.mark.live
async def test_live_mazii():
    from bunpo_analyzer.config import Settings

    d = M.MaziiDictionary.from_settings(Settings())
    r = await d.search_many(["猫"], "en")
    assert r["猫"][0].word == "猫"


async def test_cache_key_depends_on_dictionary(kho):
    from bunpo_analyzer.core.analyzer import analyze_full
    from bunpo_analyzer.core.llm import LLMClient
    from tests.test_cache import GOOD, Script, _settings

    s, cache = _settings(), C.MemoryCache()
    text = "先週姉と作ったケーキはとてもおいしかったです。"
    prov = Script([GOOD, GOOD])
    client = LLMClient(prov, s, retry_delay_s=0)
    a1 = await analyze_full(text, "vi", settings=s, kho=kho, cache=cache, client=client, dictionary=FakeDict({}))
    a2 = await analyze_full(text, "vi", settings=s, kho=kho, cache=cache, client=client)
    a3 = await analyze_full(text, "vi", settings=s, kho=kho, cache=cache, client=client, dictionary=FakeDict({}))
    assert (a1.cache, a2.cache, a3.cache) == ("miss", "miss", "hit") and len(prov.calls) == 2


# ---------------- D0: du lieu mau ----------------
def test_trim_payload_and_static_dictionary(tmp_path):
    t = M.trim_payload(neko())
    w = t["data"]["words"][0]
    assert set(w) == {"_id", "mobileId", "word", "phonetic", "level", "short_mean", "han", "means"}
    assert set(w["means"][0]) == {"mean", "kind", "stagr"}
    assert M.parse_words(t) == M.parse_words(neko())
    (tmp_path / "jaen.json").write_text(json.dumps({"queries": {"猫": t}}), encoding="utf-8")
    d = M.StaticDictionary.from_dir(tmp_path)
    r = asyncio.run(d.search_many(["猫", "犬"], "en"))
    assert list(r) == ["猫"] and r["猫"][0].level == "N5"
    assert asyncio.run(d.search_many(["猫"], "ko")) == {}


async def test_capture_script(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("mazii_capture", Path(__file__).parents[1] / "scripts" / "mazii_capture.py")
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    monkeypatch.setattr(cap, "OUT", tmp_path)
    sent = []

    def handler(req):
        q = json.loads(req.content)["query"]
        sent.append(q)
        if q == "bad":
            return httpx.Response(500)
        words = neko() if q == "猫" else {"data": {"words": []}}
        return httpx.Response(200, json={"encryptedData": encrypt(words)})

    real = httpx.AsyncClient
    monkeypatch.setattr(cap.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    st = await cap.capture("en", ["猫", "犬", "bad"], M.derive_key(PEM), "https://x", 3, 2)
    assert st["with_result"] == 1 and st["errors"] == 1 and st["new"] == 3
    saved = json.loads((tmp_path / "jaen.json").read_text(encoding="utf-8"))
    assert set(saved["queries"]) == {"猫", "犬"} and saved["errors"] == ["bad: HTTPStatusError"]
    sent.clear()
    st = await cap.capture("en", ["猫", "犬", "bad"], M.derive_key(PEM), "https://x", 3, 2)
    assert sent == ["bad"] and st["new"] == 1  # chay lai: chi thu tu loi
