"""Ham duy nhat ben ngoai can goi.

Luong (muc 2): kiem tra dau vao (1.2) -> tach tu (1.1) -> tra tu (1.4)
-> do mau ngu phap (1.5) -> goi LLM (2.1-2.2) -> kiem tra (2.3-2.4)
-> ghep ket qua (2.5) -> cache (2.6).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from bunpo_analyzer.config import SUPPORTED_LANGS, Settings, get_settings
from bunpo_analyzer.core import cache as C
from bunpo_analyzer.core import translate as TR
from bunpo_analyzer.core.assemble import assemble
from bunpo_analyzer.core.grammar_check import build_input_check
from bunpo_analyzer.core.data import Kho, get_kho
from bunpo_analyzer.core.input_check import check_input
from bunpo_analyzer.core.llm import LLMClient, LLMError
from bunpo_analyzer.core.llm.base import Message
from bunpo_analyzer.core.matcher import GrammarMatcher, get_matcher
from bunpo_analyzer.core.llm_output import LLMOutput
from bunpo_analyzer.core.pipeline import Attempt, Prepared, StageResult, analyze_llm, prepare
from bunpo_analyzer.core.prompt import need_meaning
from bunpo_analyzer.core.validator import validate
from bunpo_analyzer.schema import AnalysisResult

log = logging.getLogger("bunpo_analyzer")


@dataclass
class Analysis:
    """Ket qua kem thong tin ghi log (chi phi, model, cac cho code tu sua). App chi can `result`."""

    result: AnalysisResult
    prepared: Prepared
    stage: Optional[StageResult] = None
    notes: list[str] = field(default_factory=list)
    # off: khong dung cache | hit: lay ngay | light: cau truc tu cache + "dich nhe" | miss: phan tich moi
    cache: str = "off"

    @property
    def cost_usd(self) -> float:
        return self.stage.cost_usd if self.stage else 0.0

    @property
    def latency_ms(self) -> int:
        return self.stage.latency_ms if self.stage else 0

    def log_dict(self) -> dict:
        st = self.stage
        return {
            "id": self.result.id,
            "text": self.result.text,
            "lang": self.result.lang,
            "error": self.result.error.code if self.result.error else None,
            "check": self.result.input_check.status,
            "cache": self.cache,
            "models": [a.model for a in st.attempts] if st else [],
            "attempt_errors": [a.errors[:5] for a in st.attempts] if st else [],
            "fixes": (st.report.fixes if st and st.report else []) + self.notes,
            "misses": self.prepared.lookup.misses if self.prepared.lookup else [],
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
        }


def _lang(lang: Optional[str], settings: Settings) -> str:
    lang = (lang or settings.default_lang).lower()
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"ngon ngu '{lang}' chua ho tro; dung mot trong {', '.join(SUPPORTED_LANGS)}")
    return lang


def _attempt(r, errors: list[str]) -> Attempt:
    return Attempt(r.model, r.prompt_tokens, r.completion_tokens, r.cached_tokens, r.latency_ms, r.cost_usd, errors)


def _from_entry(p: Prepared, entry: dict) -> Optional[StageResult]:
    """Muc cache -> StageResult. Kiem tra lai bang validator; hong thi coi nhu khong co."""
    try:
        out = LLMOutput.model_validate(entry["output"])
        rep = validate(out, p.tokens, p.matches, p.input.text, lang=entry.get("lang") or p.lang)
        if not rep.ok:
            return None
        ic, _ = build_input_check(rep.output.input_check, p.input.text, p.tokens)
        return StageResult(entry["status"], output=rep.output, input_check=ic)
    except Exception as e:  # muc cu / sai khuon
        log.warning("bo muc cache hong: %s", e)
        return None


def _entry(stage: StageResult, lang: str) -> dict:
    return {"status": stage.status, "lang": lang, "output": stage.output.model_dump(),
            "model": stage.attempts[-1].model if stage.attempts else None, "at": int(time.time())}


async def _light(p: Prepared, struct: StageResult, src_lang: str, lang: str,
                 client: LLMClient, settings: Settings) -> StageResult:
    """Dich nhe: giu cau truc, chi viet lai phan chu bang ngon ngu moi.

    Model re truoc; sai (thieu, chep nguyen ban cu / tieng Nhat) thi goi model du phong kem
    danh sach loi. Van sai -> structure_failed (ben goi se phan tich lai day du).
    """
    msgs = TR.build_messages(p.input.text, p.tokens, struct.output, src_lang, lang, need_meaning(p.lookup, p.tokens))
    st = StageResult("structure_failed")
    for model in dict.fromkeys(m for m in (settings.llm_light_model, settings.llm_fallback_model) if m):
        try:
            r = await client.generate(msgs, TR.LLMTextOutput, model=model)
        except LLMError as e:
            st.error = str(e)
            continue
        out, errors = TR.merge(struct.output, r.data, lang)
        st.attempts.append(_attempt(r, errors))
        if out is not None:
            st.status, st.output = struct.status, out
            st.input_check, _ = build_input_check(out.input_check, p.input.text, p.tokens)
            return st
        msgs = msgs + [Message("assistant", r.data.model_dump_json()),
                       Message("user", "Problems:\n- " + "\n- ".join(errors) + "\nReturn the whole corrected JSON.")]
    return st


async def analyze_full(
    sentence: str,
    lang: Optional[str] = None,
    *,
    settings: Optional[Settings] = None,
    client: Optional[LLMClient] = None,
    kho: Optional[Kho] = None,
    matcher: Optional[GrammarMatcher] = None,
    cache: Optional[C.Cache] = None,
) -> Analysis:
    """Nhu `analyze` nhung tra them thong tin ghi log. Tham so phu dung cho test / chatbot tu dung san.

    cache: kho cache rieng (co get/set bat dong bo); mac dinh theo `Settings.cache_backend`.
    """
    settings = settings or get_settings()
    lang = _lang(lang, settings)
    inp = check_input(sentence, max_chars=settings.max_chars)
    if inp.error is not None:  # khong can kho, khong goi LLM
        p = Prepared(inp, lang=lang)
        return Analysis(assemble(p, None, None, lang)[0], p)
    kho = kho or get_kho(settings.data_dir)
    p = prepare(sentence, lang, kho, matcher or get_matcher(), settings.max_chars)
    cache = cache if cache is not None else C.get_cache(settings)
    base = C.base_key(p.input.text, kho.core_version, settings.llm_model)
    ttl = settings.cache_ttl_s
    state = "miss"

    # 1. Da co dung ngon ngu nay
    stage: Optional[StageResult] = None
    entry = await C.read(cache, C.text_key(base, lang))
    if entry is not None:
        stage = _from_entry(p, entry)
        state = "hit" if stage else "miss"

    if stage is None:
        try:
            client = client or LLMClient(settings=settings)
        except LLMError as e:  # sai cau hinh (thieu key, nha cung cap chua ho tro)
            log.error("LLM config: %s", e)
            stage = StageResult("llm_unavailable", error=str(e))
            client = None

    # 2. Co cau truc (thuong la ngon ngu khac) -> dich nhe
    write_struct = True
    if stage is None:
        se = await C.read(cache, C.struct_key(base))
        struct = _from_entry(p, se) if se else None
        if struct is not None:
            write_struct = False
            if se.get("lang") == lang:
                stage, state = struct, "hit"
                await C.write(cache, C.text_key(base, lang), se, ttl)
            else:
                light = await _light(p, struct, se["lang"], lang, client, settings)
                if light.status in ("ok", "grammar_error"):
                    stage, state = light, "light"
                    await C.write(cache, C.text_key(base, lang), _entry(light, lang), ttl)
                else:  # dich nhe hong -> phan tich day du, van tinh chi phi lan hong
                    log.warning("dich nhe hong (%s): %s", light.status,
                                light.error or (light.attempts[-1].errors if light.attempts else ""))
                    stage = await analyze_llm(p, client)
                    stage.attempts = light.attempts + stage.attempts

    # 3. Phan tich moi
    if stage is None:
        stage = await analyze_llm(p, client)
    if state == "miss" and stage.status in ("ok", "grammar_error"):
        e = _entry(stage, lang)
        await C.write(cache, C.text_key(base, lang), e, ttl)
        if write_struct:
            await C.write(cache, C.struct_key(base), e, ttl)

    result, notes = assemble(p, stage, kho, lang)
    a = Analysis(result, p, stage, notes, state)
    log.info("analyze %s", a.log_dict())
    return a


async def analyze(
    sentence: str,
    lang: Optional[str] = None,
    provider: Optional[str] = None,
) -> AnalysisResult:
    """Phan tich DUNG 1 cau tieng Nhat (chatbot da loc dau vao).

    lang: ngon ngu nguoi dung, mac dinh `Settings.default_lang`.
    provider: nha cung cap LLM, mac dinh `Settings.llm_provider`.
    Khong nem loi khi LLM hong: tra ket qua co `error` (muc 11.5).
    """
    settings = get_settings()
    if provider and provider != settings.llm_provider:
        settings = settings.model_copy(update={"llm_provider": provider})
    return (await analyze_full(sentence, lang, settings=settings)).result
