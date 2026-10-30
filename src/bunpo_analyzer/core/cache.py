"""Cache ket qua (buoc 2.6, muc 3.6 + 12.5 file ke hoach).

Luu dau ra LLM DA KIEM TRA (vi tri theo token), khong luu AnalysisResult: phan
token, nghia tu kho, ngu phap kho duoc ghep lai moi lan (re, vai ms) nen sua kho
(nghia, ban dich) la hien ngay ma khong phai xoa cache.

Hai loai muc:
- s:<khoa>        cau truc cau + chu cua ngon ngu dau tien (ghi kem lang)
- t:<khoa>:<lang> ban day du cho tung ngon ngu

Khoa = cau da chuan hoa + khuon ket qua + prompt + kho goc (word_lib, grammar_lib)
+ bo luat do mau + tu dien tach tu + model chinh. Doi bat ky thu nao -> khoa moi,
muc cu tu het han (TTL), khong can xoa tay.

Chi luu cau phan tich duoc (ok / suspect / grammar_error). Loi LLM, sai khuon
khong luu de lan sau thu lai.

Kho luu: `memory` (mac dinh, trong tien trinh) hoac `redis` (dung chung nhieu
worker). Chatbot co the truyen kho rieng: chi can co `get` / `set` bat dong bo.
Cache hong (redis mat ket noi...) thi bo qua, van phan tich binh thuong.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any, Optional, Protocol

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.prompt import PROMPT_VERSION
from bunpo_analyzer.schema import SCHEMA_VERSION

log = logging.getLogger("bunpo_analyzer.cache")

# Tang khi doi code anh huong dau ra da luu (tach cum, doi vi tri...) ma khong doi prompt.
CACHE_VERSION = "1"
PREFIX = "bunpo:"
_RULES = Path(__file__).resolve().parent.parent / "rules"


class Cache(Protocol):
    async def get(self, key: str) -> Optional[str]: ...

    async def set(self, key: str, value: str, ttl_s: int) -> None: ...


class MemoryCache:
    """LRU co han dung, trong mot tien trinh. Mat khi khoi dong lai."""

    def __init__(self, max_items: int = 5000) -> None:
        self.max_items = max_items
        self._d: OrderedDict[str, tuple[float, str]] = OrderedDict()

    async def get(self, key: str) -> Optional[str]:
        item = self._d.get(key)
        if item is None:
            return None
        exp, val = item
        if exp < time.time():
            del self._d[key]
            return None
        self._d.move_to_end(key)
        return val

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self._d[key] = (time.time() + ttl_s, value)
        self._d.move_to_end(key)
        while len(self._d) > self.max_items:
            self._d.popitem(last=False)

    def __len__(self) -> int:
        return len(self._d)


class RedisCache:
    """Can `pip install bunpo-analyzer[redis]`."""

    def __init__(self, url: str) -> None:
        try:
            import redis.asyncio as redis
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("cache_backend=redis can cai them: pip install 'bunpo-analyzer[redis]'") from e
        self._r = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        await self._r.set(key, value, ex=ttl_s)


class NoCache:
    async def get(self, key: str) -> Optional[str]:
        return None

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        return None


_stores: dict[tuple, Cache] = {}


def get_cache(settings: Settings) -> Cache:
    k = (settings.cache_backend, settings.cache_url, settings.cache_max_items)
    if k not in _stores:
        b = settings.cache_backend
        if b == "memory":
            _stores[k] = MemoryCache(settings.cache_max_items)
        elif b == "redis":
            _stores[k] = RedisCache(settings.cache_url)
        elif b == "none":
            _stores[k] = NoCache()
        else:
            raise ValueError(f"cache_backend '{b}' khong hop le (memory | redis | none)")
    return _stores[k]


# ---------------- khoa ----------------
@lru_cache(maxsize=1)
def rules_version() -> str:
    h = hashlib.sha256()
    for p in sorted(_RULES.glob("*.json")) + [_RULES.parent / "tables" / "grammar_canon.json"]:
        if not p.exists():
            continue
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def dict_version() -> str:
    try:
        return metadata.version("sudachidict-core") + "/" + metadata.version("sudachipy")
    except metadata.PackageNotFoundError:  # pragma: no cover
        return "?"


def base_key(text: str, kho_version: str, model: str) -> str:
    parts = [CACHE_VERSION, SCHEMA_VERSION, PROMPT_VERSION, kho_version, rules_version(), dict_version(), model, text]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def struct_key(base: str) -> str:
    return f"{PREFIX}s:{base}"


def text_key(base: str, lang: str) -> str:
    from bunpo_analyzer.core.translate import TRANSLATE_VERSION

    return f"{PREFIX}t:{base}:{lang}:{TRANSLATE_VERSION}"


# ---------------- doc / ghi an toan ----------------
async def read(cache: Cache, key: str) -> Optional[dict[str, Any]]:
    try:
        raw = await cache.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:  # cache hong khong duoc lam hong phan tich
        log.warning("cache doc loi %s: %s", key, e)
        return None


async def write(cache: Cache, key: str, value: dict[str, Any], ttl_s: int) -> None:
    try:
        await cache.set(key, json.dumps(value, ensure_ascii=False), ttl_s)
    except Exception as e:
        log.warning("cache ghi loi %s: %s", key, e)
