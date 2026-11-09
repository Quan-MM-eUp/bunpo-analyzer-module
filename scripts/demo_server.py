"""Trang test module tren may (giao dien chat, ket qua trinh bay nhu artifact).

    pip install -e ".[demo]"
    python scripts/demo_server.py            # mo http://localhost:8000
    python scripts/demo_server.py --port 8080

Goi module THAT: analyze_full() (key trong .env) va grammar_detail(). Chi nghe tren
127.0.0.1 (may khac trong mang khong vao duoc); key khong bao gio gui xuong trinh duyet.
Cache trong bo nho: gui lai cau cu thi co ngay, khong ton tien; tat bang menu "Bo qua cache".

API (giai doan 5 se lam ban that trong chatbot):
    GET  /api/health
    POST /api/analyze        {"text": "...", "lang": "vi", "no_cache": false} -> {"result": AnalysisResult, "meta": {...}}
    GET  /api/grammar/{id}?lang=vi                                         -> GrammarDetail
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
except ImportError:  # pragma: no cover
    sys.exit('Thieu FastAPI: chay  pip install -e ".[demo]"')

from bunpo_analyzer.config import SUPPORTED_LANGS, Settings
from bunpo_analyzer.core.analyzer import analyze_full
from bunpo_analyzer.core.cache import MemoryCache, NoCache
from bunpo_analyzer.core.data import Kho, get_kho
from bunpo_analyzer.core.grammar_detail import grammar_detail
from bunpo_analyzer.core.labels import label_langs, labels
from bunpo_analyzer.core.ready import check_ready

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "demo" / "app.html"
log = logging.getLogger("bunpo_demo")


class AnalyzeIn(BaseModel):
    text: str
    lang: str = "vi"
    no_cache: bool = False


def page_html() -> str:
    """Trang chat (demo/app.html) boc trong khung HTML day du; MOCK = null -> goi API that."""
    body = PAGE.read_text(encoding="utf-8").replace("/*LABELS*/null", json.dumps(
        {lg: labels(lg) for lg in label_langs()}, ensure_ascii=False).replace("</", "<\\/"))
    return ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>'
            + body + "</body></html>")


def create_app(settings: Optional[Settings] = None, kho: Optional[Kho] = None, client=None) -> FastAPI:
    """client: LLMClient gia cho test; mac dinh analyze_full tu tao theo settings."""
    settings = settings or Settings()
    kho = kho or get_kho(settings.data_dir)
    cache = MemoryCache(settings.cache_max_items)
    app = FastAPI(title="Bunpo Test", docs_url="/api/docs", redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page_html()  # doc lai moi lan: sua app.html la thay ngay, khong can khoi dong lai

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "model": settings.llm_model, "fallback": settings.llm_fallback_model,
                "light_model": settings.llm_light_model, "has_key": bool(settings.openai_api_key),
                "kho_version": kho.core_version, "grammar": len(kho.grammars), "dict": settings.dict_provider}

    @app.post("/api/analyze")
    async def analyze(body: AnalyzeIn) -> dict:
        if body.lang not in SUPPORTED_LANGS:
            raise HTTPException(400, f"lang '{body.lang}' khong ho tro")
        a = await analyze_full(body.text, body.lang, settings=settings, kho=kho, client=client,
                               cache=NoCache() if body.no_cache else cache)
        info = a.log_dict()
        meta = {"cache": a.cache, "models": info["models"], "latency_ms": a.latency_ms, "cost_usd": a.cost_usd,
                "attempt_errors": info["attempt_errors"], "fixes": info["fixes"], "misses": info["misses"]}
        log.info("%s | %s | cache=%s | %.1fs | $%.4f", body.lang, body.text[:40], a.cache, a.latency_ms / 1000, a.cost_usd)
        return {"result": a.result.model_dump(mode="json", exclude_none=True), "meta": meta}

    @app.get("/api/ready")
    async def ready() -> dict:
        return await check_ready(settings)

    @app.get("/api/labels")
    def ui_labels(lang: str = "vi") -> dict:
        return labels(lang)

    @app.get("/api/grammar/{gid}")
    def grammar(gid: int, lang: str = "vi") -> dict:
        d = grammar_detail(gid, lang if lang in SUPPORTED_LANGS else "vi", kho)
        if d is None:
            raise HTTPException(404, f"khong co mau #{gid}")
        return d.model_dump(mode="json")

    return app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    settings = Settings()
    if not settings.openai_api_key:
        print("Canh bao: thieu BUNPO_OPENAI_API_KEY trong .env -> cau moi se bao 'khong goi duoc AI'.")
    import uvicorn

    print(f"Mo http://localhost:{a.port}  (Ctrl+C de dung)")
    uvicorn.run(create_app(settings), host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
