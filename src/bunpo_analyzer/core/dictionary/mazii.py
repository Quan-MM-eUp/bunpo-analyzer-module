"""Client API tra tu Mazii (POST /api/search/word/v3, ket qua ma hoa AES-256-CBC).

Khoa AES = PBKDF2-HMAC-SHA256(password = noi dung public.pem bo xuong dong, salt "mazii-search-v3",
10000 vong, 32 byte). Response: {"encryptedData": "<iv_b64>:<ciphertext_b64>"} -> JSON
{"status", "data": {"words": [...]}}.

- Moi tu cache rieng (khoa = tu dien + tu), loi / qua gio khong cache.
- Goi song song co gioi han (dict_max_concurrency), moi lan goi <= dict_timeout_s.
- Loi lien tiep >= 5 lan: ngung goi 60 giay (tra rong ngay) de khong lam cham phan tich.
Khong bao gio ghi noi dung public.pem / khoa vao log.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from bunpo_analyzer.core.dictionary.base import DictEntry, Sense

log = logging.getLogger("bunpo_analyzer.dict")

# Ngon ngu module -> bo tu dien Mazii. Khong co tu dien thi dung tieng Anh.
MAZII_DICTS: dict[str, str] = {
    "vi": "javi", "en": "jaen", "cn": "jacn", "tw": "jatw", "ko": "jako", "id": "jaid", "es": "jaes",
    "fr": "jafr", "ru": "jaru", "my": "jamy", "pt": "japt", "de": "jade", "th": "jath", "hi": "jahi",
    "ne": "jane", "pl": "jaen",
}
SALT = b"mazii-search-v3"
ITERATIONS = 10000
CACHE_PREFIX = "bunpo:d:"
EMPTY_TTL_S = 86400  # khong co ket qua: cache 1 ngay (kho co the duoc bo sung)
BREAKER_FAILS = 5
BREAKER_PAUSE_S = 60.0


def derive_key(pem_text: str) -> bytes:
    password = pem_text.strip().replace("\n", "").replace("\r", "").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", password, SALT, ITERATIONS, 32)


def decrypt_payload(encrypted: str, key: bytes) -> Any:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    iv_b64, ct_b64 = encrypted.split(":", 1)
    dec = Cipher(algorithms.AES(key), modes.CBC(base64.b64decode(iv_b64))).decryptor()
    raw = dec.update(base64.b64decode(ct_b64)) + dec.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return json.loads((unpad.update(raw) + unpad.finalize()).decode("utf-8"))


def _kinds(kind: Optional[str]) -> tuple[str, ...]:
    return tuple(k.strip() for k in (kind or "").split(",") if k.strip())


def parse_words(payload: Any) -> list[DictEntry]:
    """JSON da giai ma -> danh sach DictEntry (bo cac truong khong dung: anh, trong am, vi du...)."""
    data = (payload or {}).get("data") or {}
    out = []
    for w in data.get("words") or []:
        if not isinstance(w, dict) or not w.get("word"):
            continue
        lv = w.get("level")
        level = (lv[0] if lv else None) if isinstance(lv, list) else (lv or None)
        senses = tuple(
            Sense(str(m.get("mean") or "").strip(), _kinds(m.get("kind")), tuple(m.get("stagr") or ()))
            for m in w.get("means") or [] if isinstance(m, dict) and (m.get("mean") or "").strip()
        )
        out.append(DictEntry(
            id=str(w.get("_id") or w.get("mobileId") or ""), word=str(w["word"]),
            readings=tuple(x for x in str(w.get("phonetic") or "").split() if x),
            level=level, han=(w.get("han") or None), short_mean=(w.get("short_mean") or None), senses=senses,
        ))
    return out


class MaziiDictionary:
    """Dictionary dung Mazii. cache: kho cache bat dong bo (get/set) cua module; http: httpx.AsyncClient."""

    def __init__(self, pem_text: str, *, url: str = "https://mazii.net/api/search/word/v3", limit: int = 3,
                 timeout_s: float = 1.5, max_concurrency: int = 8, cache=None, cache_ttl_s: int = 30 * 86400,
                 http=None) -> None:
        if not pem_text or not pem_text.strip():
            raise ValueError("Thieu noi dung public.pem cho Mazii")
        self._key = derive_key(pem_text)
        self.url, self.limit, self.timeout_s = url, limit, timeout_s
        self.cache, self.cache_ttl_s = cache, cache_ttl_s
        self._sem = asyncio.Semaphore(max_concurrency)
        self._http = http
        self._fails = 0
        self._paused_until = 0.0
        self.stats = {"calls": 0, "cache_hits": 0, "errors": 0, "skipped": 0}

    @classmethod
    def from_settings(cls, settings, cache=None, http=None) -> MaziiDictionary:
        pem = settings.mazii_pem or Path(settings.mazii_pem_path).read_text(encoding="utf-8")
        return cls(pem, url=settings.mazii_url, limit=settings.mazii_limit, timeout_s=settings.dict_timeout_s,
                   max_concurrency=settings.dict_max_concurrency, cache=cache, cache_ttl_s=settings.dict_cache_ttl_s,
                   http=http)

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.AsyncClient(timeout=self.timeout_s, headers={"Content-Type": "application/json"})
        return self._http

    async def _cache_get(self, key: str) -> Optional[list[DictEntry]]:
        if self.cache is None:
            return None
        try:
            raw = await self.cache.get(key)
        except Exception as e:  # noqa: BLE001 - cache hong khong duoc lam hong tra tu
            log.warning("cache tu dien doc loi: %s", e)
            return None
        if raw is None:
            return None
        return [DictEntry.from_json(x) for x in json.loads(raw)]

    async def _cache_set(self, key: str, entries: list[DictEntry]) -> None:
        if self.cache is None:
            return
        try:
            await self.cache.set(key, json.dumps([e.to_json() for e in entries], ensure_ascii=False),
                                 self.cache_ttl_s if entries else EMPTY_TTL_S)
        except Exception as e:  # noqa: BLE001
            log.warning("cache tu dien ghi loi: %s", e)

    async def _fetch(self, query: str, dict_code: str) -> Optional[list[DictEntry]]:
        if time.monotonic() < self._paused_until:
            self.stats["skipped"] += 1
            return None
        async with self._sem:
            self.stats["calls"] += 1
            try:
                r = await asyncio.wait_for(
                    self._client().post(self.url, json={"dict": dict_code, "query": query, "limit": self.limit}),
                    self.timeout_s)
                r.raise_for_status()
                body = r.json()
                payload = decrypt_payload(body["encryptedData"], self._key) if "encryptedData" in body else body
                entries = parse_words(payload)
            except Exception as e:  # noqa: BLE001 - mang, giai ma, khuon: deu coi la khong tra duoc
                self.stats["errors"] += 1
                self._fails += 1
                if self._fails >= BREAKER_FAILS:
                    self._paused_until = time.monotonic() + BREAKER_PAUSE_S
                    log.error("Mazii loi %d lan lien tiep, tam ngung %ds: %s", self._fails, BREAKER_PAUSE_S,
                              type(e).__name__)
                else:
                    log.warning("Mazii loi '%s' (%s): %s", query, dict_code, type(e).__name__)
                return None
        self._fails = 0
        return entries

    async def search(self, query: str, lang: str) -> Optional[list[DictEntry]]:
        dict_code = MAZII_DICTS.get(lang, "jaen")
        key = f"{CACHE_PREFIX}{dict_code}:{query}"
        hit = await self._cache_get(key)
        if hit is not None:
            self.stats["cache_hits"] += 1
            return hit
        entries = await self._fetch(query, dict_code)
        if entries is not None:
            await self._cache_set(key, entries)
        return entries

    async def search_many(self, queries: list[str], lang: str) -> dict[str, list[DictEntry]]:
        """Goi song song; het han tong (2 x timeout) thi bo cac tu chua xong (khong cho them)."""
        qs = list(dict.fromkeys(q for q in queries if q))
        if not qs:
            return {}
        tasks = {asyncio.ensure_future(self.search(q, lang)): q for q in qs}
        done, pending = await asyncio.wait(tasks, timeout=self.timeout_s * 2)
        for t in pending:
            t.cancel()
        if pending:
            log.warning("Mazii qua gio %d/%d tu", len(pending), len(qs))
        out = {}
        for t in done:
            r = t.result() if not t.cancelled() and t.exception() is None else None
            if r is not None:
                out[tasks[t]] = r
        return out

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
