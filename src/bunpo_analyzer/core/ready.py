"""Kiem tra cau hinh khi khoi dong (backend goi 1 lan, ghi log / tra ve health check).

    from bunpo_analyzer import check_ready
    rep = await check_ready()            # khong goi mang
    rep = await check_ready(ping=True)   # goi thu Mazii (1 tu) va Redis
    if not rep["ok"]: ...                # rep["checks"][ten] = {"ok", "detail"[, "warn"]}

ok = False khi thieu thu bat buoc (kho, tach tu, LLM, cache). Tu dien Mazii hong chi la canh bao
(warn): module tu quay ve kho word_lib. Khong bao gio ghi noi dung key / public.pem.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from bunpo_analyzer.config import Settings, get_settings


def _ok(detail: str, **kw: Any) -> dict[str, Any]:
    return {"ok": True, "detail": detail, **kw}


def _fail(detail: str) -> dict[str, Any]:
    return {"ok": False, "detail": detail}


async def check_ready(settings: Optional[Settings] = None, ping: bool = False) -> dict[str, Any]:
    s = settings or get_settings()
    checks: dict[str, dict[str, Any]] = {}

    try:
        from bunpo_analyzer.core.data import get_kho

        kho = get_kho(s.data_dir)
        fb = s.text_fallback_lang
        detail = (f"{len(kho.grammars)} mau ngu phap, {len(kho.words)} tu; ban dich kho: "
                  f"{', '.join(x for x in kho.langs if x != 'vi') or 'chua co'}; ngon ngu du phong: {fb}")
        extra: dict[str, Any] = {"langs": list(kho.langs), "text_fallback": fb}
        if fb != "vi" and fb not in kho.langs:
            # Dat BUNPO_TEXT_FALLBACK_LANG nhung quen trien khai grammar_text.<fb>.json: ngon ngu chua dich
            # se hien tieng Viet. Khong chan khoi dong (kho van dung duoc), chi canh bao.
            detail += f" (THIEU grammar/grammar_text.{fb}.json -> dang dung tieng Viet)"
            extra["warn"] = True
        checks["kho"] = _ok(detail, **extra)
    except Exception as e:  # noqa: BLE001
        checks["kho"] = _fail(f"khong nap duoc kho o BUNPO_DATA_DIR={s.data_dir}: {type(e).__name__}: {e}")

    try:
        from bunpo_analyzer.core.matcher import get_matcher
        from bunpo_analyzer.core.tokenizer import tokenize

        n = len(tokenize("今日は雨です。"))
        checks["tokenizer"] = _ok(f"SudachiPy ok ({n} token), {len(get_matcher().rules)} luat")
    except Exception as e:  # noqa: BLE001
        checks["tokenizer"] = _fail(f"{type(e).__name__}: {e}")

    if s.llm_provider != "openai":
        checks["llm"] = _fail(f"llm_provider '{s.llm_provider}' chua ho tro (chi openai)")
    elif not s.openai_api_key:
        checks["llm"] = _fail("thieu BUNPO_OPENAI_API_KEY")
    else:
        checks["llm"] = _ok(f"openai {s.openai_base_url}: {s.llm_model} (du phong {s.llm_fallback_model}, "
                            f"dich nhe {s.llm_light_model})")

    try:
        from bunpo_analyzer.core.cache import get_cache

        c = get_cache(s)
        if ping and s.cache_backend == "redis":
            await c.set("bunpo:ready", "1", 60)
            assert await c.get("bunpo:ready") == "1"
        checks["cache"] = _ok(s.cache_backend + (" (da ping)" if ping and s.cache_backend == "redis" else ""))
    except Exception as e:  # noqa: BLE001
        checks["cache"] = _fail(f"{s.cache_backend}: {type(e).__name__}: {e}")

    if s.dict_provider != "mazii":
        checks["dictionary"] = _ok("kho word_lib (BUNPO_DICT_PROVIDER=kho)")
    else:
        from bunpo_analyzer.core.analyzer import get_dictionary

        d = get_dictionary(s)
        if d is None:
            checks["dictionary"] = _ok("Mazii khong dung duoc (thieu / hong public.pem: BUNPO_MAZII_PEM_PATH hoac "
                                       "BUNPO_MAZII_PEM) -> dang dung kho word_lib", warn=True)
        elif ping:
            t = time.perf_counter()
            r = await d.search("猫", "en")
            ms = round((time.perf_counter() - t) * 1000)
            checks["dictionary"] = (_ok(f"Mazii ok ({ms} ms)") if r else
                                    _ok(f"Mazii khong tra loi ({ms} ms) -> tu tam dung, dung LLM cho nghia tu",
                                        warn=True))
        else:
            checks["dictionary"] = _ok("Mazii (public.pem doc duoc; ping=True de goi thu)")

    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}
