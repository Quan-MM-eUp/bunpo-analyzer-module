"""Dich kho ngu phap bang Claude API (thay cho tac tu Cowork) - ke-hoach-dich-kho-ngu-phap.md.

Chay tren may nguoi dung, trong thu muc "Model bunpo":

    pip install anthropic
    python bunpo-analyzer/scripts/translation/api_translate.py tw --n 20 --max-usd 20
    python bunpo-analyzer/scripts/translation/api_translate.py en --batches b002,b050 --pilot translation/pilot_api

Moi lo: Opus dich (chia 2-3 yeu cau) -> check.py, loi thi gui lai sua (<= 2 lan) -> Sonnet cham
(hi/ne/my them Opus dich nguoc) -> muc loi nang: Opus sua + cham lai (<= 2 vong) -> qa.py ghi diem,
tm.py cap nhat tien do. Dung chung khoa / manifest voi Cowork (khong dich trung ngon ngu).

--pilot DIR: chay thu - chep nguon / thuat ngu / van phong vao DIR va ghi ket qua o do; khong nhan
khoa, khong dung manifest, khong dong vao translation/out (an toan voi lo Cowork da dich).

Key: bien moi truong ANTHROPIC_API_KEY, hoac dong ANTHROPIC_API_KEY=... trong .env (--env, mac dinh
bunpo-analyzer/.env). Khong bao gio in key.
Chi phi tung yeu cau: reports/<lang>/api_usage.csv (pilot: DIR/reports/...).
Ma thoat: 0 xong, 1 loi, 2 khoa dang bi giu, 3 dung vi cham --max-usd.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm
from check import check_batch
from common import (
    LANG_NAMES,
    LANGS,
    LOW_RESOURCE,
    read_json,
    workspace,
    write_json,
    write_text,
)
from qa import apply_batch, render_md

PROMPT_VER = "api-1"
MODEL_T = "claude-opus-5-5"
MODEL_J = "claude-sonnet-5-5"
# USD / 1 trieu token: vao, ra, ghi cache (5 phut), doc cache  (bang gia platform.claude.com, 11/2026)
PRICES = {"opus": (4.0, 20.0, 5.0, 0.20), "sonnet": (2.0, 10.0, 2.5, 0.10), "haiku": (1.0, 5.0, 1.25, 0.10)}
MAX_TOKENS = 32000
CHUNK_CHARS = 10000
MAX_REPAIR = 2
MAX_FIX = 2
ROOT = Path(__file__).resolve().parents[2]  # bunpo-analyzer/


class BudgetExceeded(Exception):
    pass


# ---------------- goi API ----------------
class Usage:
    """Cong don token / chi phi, ghi tung yeu cau vao CSV (an toan nhieu luong)."""

    def __init__(self, csv_path: Path | None, max_usd: float | None):
        self.lock = threading.Lock()
        self.usd = 0.0
        self.tokens = {"in": 0, "cache_write": 0, "cache_read": 0, "out": 0}
        self.max_usd = max_usd
        self.csv_path = csv_path

    @staticmethod
    def price(model: str) -> tuple[float, float, float, float]:
        for k, v in PRICES.items():
            if k in model:
                return v
        return PRICES["opus"]

    def add(self, model: str, u: dict, batch: str, stage: str) -> float:
        pi, po, pw, pr = self.price(model)
        usd = (u["in"] * pi + u["out"] * po + u["cache_write"] * pw + u["cache_read"] * pr) / 1e6
        with self.lock:
            self.usd += usd
            for k in self.tokens:
                self.tokens[k] += u[k]
            if self.csv_path:
                new = not self.csv_path.exists()
                self.csv_path.parent.mkdir(parents=True, exist_ok=True)
                with self.csv_path.open("a", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    if new:
                        w.writerow(["time", "batch", "stage", "model", "in", "cache_write", "cache_read", "out", "usd"])
                    w.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), batch, stage, model,
                                u["in"], u["cache_write"], u["cache_read"], u["out"], f"{usd:.4f}"])
        return usd

    def over(self) -> bool:
        return self.max_usd is not None and self.usd >= self.max_usd


class Claude:
    """Goi Messages API (stream de cho phep cau tra loi dai). client: anthropic.Anthropic hoac gia cho test."""

    def __init__(self, client, usage: Usage):
        self.client = client
        self.usage = usage

    def call(self, model: str, system: str, user: str, batch: str, stage: str,
             max_tokens: int = MAX_TOKENS) -> tuple[str, str]:
        if self.usage.over():
            raise BudgetExceeded
        sysblocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        with self.client.messages.stream(model=model, max_tokens=max_tokens, system=sysblocks,
                                         messages=[{"role": "user", "content": user}]) as s:
            msg = s.get_final_message()
        u = msg.usage
        self.usage.add(model, {"in": u.input_tokens or 0, "out": u.output_tokens or 0,
                               "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
                               "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0}, batch, stage)
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        return text, msg.stop_reason or ""


def parse_json(text: str) -> dict:
    """Lay doi tuong JSON dau tien trong cau tra loi (bo ```json neu co)."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    i = t.find("{")
    if i < 0:
        raise ValueError("khong thay JSON")
    obj, _ = json.JSONDecoder().raw_decode(t[i:])
    if not isinstance(obj, dict):
        raise TypeError("JSON khong phai doi tuong")
    return obj


# ---------------- loi nhac ----------------
FIELD_RULES = """\
Translate every key of `fields` and nothing else (`context` is only there to help you understand the grammar point):
- `name`, `connection` (`mode: "vi_parts"`): translate ONLY the Vietnamese words; Japanese, symbols and brackets stay exactly.
- `meaning`, `explain`, `notes`: `src` tells the source language ("vi" Vietnamese, "ja" Japanese, "en" English); translate from it.
- `examples` (`[{jp, vi}]`): translate FROM THE JAPANESE sentence `jp` (the `vi` line is only a hint, sometimes wrong). Output a list of strings, same length and order.
- `mistakes` (`[{src, text}]`): list of strings, same length and order. A line that is only a Japanese correction (`× 学生ですかもしれない → ○ 学生かもしれない`) is copied unchanged; if it contains Vietnamese words (also Vietnamese written without diacritics, e.g. "Sai chia: …"), translate those words and keep the Japanese.
- `comparison` (`{headers, rows}`): same table size; translate cell by cell; a cell with only Japanese / symbols is copied unchanged; empty cells stay empty. Vietnamese without diacritics ("cho", "Sau khi", "Cao", "A hay B") is still Vietnamese: translate it."""

RULES = """\
1. Faithful: translate what the source says. Do not add, drop, correct or "improve" content, even if the source looks wrong or repetitive. Keep line breaks, bullets, numbering, ×/○/✓/→/～ and sentence order.
2. Keep Japanese exactly: every Japanese word or phrase inside the text (kana, kanji, 「」 quotes, ～ている, Vて) and every <ruby>…<rt>…</rt></ruby> tag, character for character. Never romanize Japanese.
3. Notation stays: V, N, A, Aい, Aな, Na, S, Vる/Vて/Vた/Vない/Vます, N1/N2, A/B labels.
4. Glossary terms are mandatory: when the source uses a glossary term (any Vietnamese variant), use its term or an accepted alternative (inflect naturally).
5. Natural {LANG_NAME} in the register of the style guide; example sentences must read like a teacher's natural translation, not word-by-word.
6. Examples keep the Japanese tense/aspect, person and number; do not invent gender (use neutral wording) or add nuances.
7. No Vietnamese may remain in the output."""

OUTPUT_T = """\
Return ONLY a JSON object, no commentary, no markdown fence:
{"items": [{"id": <id>, "fields": {<exactly the input field keys>}}]}
One output item per input item, same order. Text fields are strings; `examples` and `mistakes` are lists of strings; `comparison` is {"headers": [...], "rows": [[...]]}."""

JUDGE_RULES = """\
You are an independent reviewer of a translation into {LANG_NAME} ({LANG}) made by another model. Compare every field of every item with its source (fields with src "vi" are Vietnamese, "ja" Japanese, "en" English; `examples` must be translated from the Japanese `jp` sentence). Code checks already passed (structure, kept Japanese, script) - focus on meaning and language.

Record each real problem as an issue:
- category: accuracy (wrong / missing / added meaning, mistranslated example, wrong grammar explanation) | terminology (glossary term not used, wrong grammar term) | fluency (ungrammatical, unnatural, wrong script / variant) | style (register, inconsistency with the style guide) | format (lost line breaks or symbols, Japanese changed)
- severity: minor (reader still understands correctly) | major (meaning distorted, misleading for a learner, clearly wrong term) | critical (opposite / harmful meaning, untranslated or garbage field)
- field (e.g. explain, examples[2], comparison[r1.2]), a short note in English, and a concrete fix (the corrected text for that span).

A glossary term is correct when the translation uses its term or any accepted alternative (inflected as needed). A Japanese-only correction line copied unchanged is correct. Faithfulness is the standard: do not penalise content faithfully carried over from a clumsy source; do not ask for additions. Be strict but fair: real problems, not taste; report every major/critical issue.
{BACKTRANSLATION}
Return ONLY a JSON object: {"items": [{"id": <id>, "issues": [{"field", "category", "severity", "note", "fix"}]}], "summary": "<2-3 sentences>"} with one entry per item (empty issues list if none)."""

BT = ("Because this is a low-resource language, for every meaning / explain / notes field and each example, first "
      "back-translate the translation into Vietnamese (in your reasoning) and compare it with the source meaning; any "
      "divergence in meaning is an accuracy issue.")


def glossary_lines(ws: Path, lang: str) -> str:
    out = []
    for t in read_json(ws / "glossary" / f"{lang}.json")["terms"]:
        line = f"{' / '.join(t['vi'])} ({t['ja']}) → {t['tr']}"
        if t.get("accept"):
            line += f"  (also: {', '.join(t['accept'])})"
        if t.get("note"):
            line += f"  [{t['note']}]"
        out.append(line)
    return "\n".join(out)


def system_translate(ws: Path, lang: str) -> str:
    name = LANG_NAMES[lang]
    return (f"You translate entries of a Japanese-grammar database (Migii JLPT app) from Vietnamese (sometimes "
            f"Japanese or English) into {name} ({lang}). Readers are {name}-speaking learners of Japanese (JLPT N5-N1).\n\n"
            f"# Field rules\n{FIELD_RULES}\n\n# Rules\n{RULES.replace('{LANG_NAME}', name)}\n\n"
            f"# Glossary (Vietnamese variants (Japanese) → mandatory {name} term)\n{glossary_lines(ws, lang)}\n\n"
            f"# Style guide\n{(ws / 'style' / f'{lang}.md').read_text(encoding='utf-8')}\n\n# Output\n{OUTPUT_T}")


def system_judge(ws: Path, lang: str, backtranslate: bool) -> str:
    name = LANG_NAMES[lang]
    rules = JUDGE_RULES.replace("{LANG_NAME}", name).replace("{LANG}", lang).replace(
        "{BACKTRANSLATION}", ("\n" + BT + "\n") if backtranslate else "")
    return (f"{rules}\n\n# Glossary (Vietnamese variants (Japanese) → mandatory {name} term)\n{glossary_lines(ws, lang)}\n\n"
            f"# Style guide\n{(ws / 'style' / f'{lang}.md').read_text(encoding='utf-8')}")


def src_view(si: dict) -> dict:
    return {"id": si["id"], "level": si.get("level"), "context": si.get("context"), "fields": si["fields"]}


def chunks(items: list[dict], max_chars: int) -> list[list[dict]]:
    out, cur, n = [], [], 0
    for it in items:
        k = len(json.dumps(it["fields"], ensure_ascii=False))
        if cur and n + k > max_chars:
            out.append(cur)
            cur, n = [], 0
        cur.append(it)
        n += k
    if cur:
        out.append(cur)
    return out


# ---------------- mot lo ----------------
class BatchJob:
    def __init__(self, ws: Path, lang: str, batch: str, llm: Claude, mt: str, mj: str, chunk_chars: int, date: str):
        self.ws, self.lang, self.batch, self.llm = ws, lang, batch, llm
        self.mt, self.mj, self.chunk_chars, self.date = mt, mj, chunk_chars, date
        self.src = read_json(ws / "source" / f"{batch}.json")["items"]
        self.by_id = {si["id"]: si for si in self.src}
        self.sys_t = system_translate(ws, lang)
        self.low = lang in LOW_RESOURCE
        self.log: list[str] = []

    # --- dich ---
    def translate_items(self, items: list[dict], stage: str = "dich") -> dict[int, dict]:
        """Dich mot nhom muc; cau tra loi bi cat (max_tokens) hoac JSON hong -> chia doi / thu lai."""
        user = ("Translate these items.\n\n```json\n"
                + json.dumps([src_view(i) for i in items], ensure_ascii=False, indent=1) + "\n```")
        for attempt in range(2):
            text, stop = self.llm.call(self.mt, self.sys_t, user, self.batch, stage)
            if stop == "max_tokens" and len(items) > 1:
                h = len(items) // 2
                return {**self.translate_items(items[:h], stage), **self.translate_items(items[h:], stage)}
            try:
                got = {int(x["id"]): x.get("fields") or {} for x in parse_json(text).get("items", [])}
            except (ValueError, KeyError, TypeError) as e:
                self.log.append(f"{stage}: JSON hong lan {attempt + 1}: {e}")
                continue
            miss = [i for i in items if i["id"] not in got]
            if miss and len(miss) < len(items):
                got.update(self.translate_items(miss, stage))
            return got
        if len(items) > 1:
            h = len(items) // 2
            return {**self.translate_items(items[:h], stage), **self.translate_items(items[h:], stage)}
        return {}

    def write_out(self, fields: dict[int, dict]) -> None:
        items = [{"id": si["id"], "src_hash": si["src_hash"], "fields": fields.get(si["id"], {})} for si in self.src]
        write_json(self.ws / "out" / self.lang / f"{self.batch}.json",
                   {"batch": self.batch, "lang": self.lang, "model": self.mt, "prompt_ver": PROMPT_VER,
                    "date": self.date, "items": items})

    def check_errors(self) -> dict[int, list[str]]:
        r = check_batch(self.ws, self.lang, self.batch)
        out: dict[int, list[str]] = {}
        for e in r["errors"]:
            m = re.match(r"#(\d+)", e)
            if m:
                out.setdefault(int(m.group(1)), []).append(e)
            else:
                out.setdefault(-1, []).append(e)
        return out

    def revise(self, fields: dict[int, dict], problems: dict[int, list], stage: str, what: str) -> dict[int, dict]:
        """Gui muc + ban dich hien tai + van de, nhan lai cac truong da sua (gia tri day du)."""
        payload = [{"source": src_view(self.by_id[i]), "current_translation": fields.get(i, {}), what: p}
                   for i, p in problems.items() if i in self.by_id]
        if not payload:
            return {}
        user = (f"Your earlier translation of these items has problems ({what}). For each problem: if it is real, fix it; "
                "if it is wrong (e.g. asks for content not in the source), keep the text. Return ONLY a JSON object "
                '{"items": [{"id": <id>, "fields": {<only the fields you changed, each with its FULL new value>}}]}.'
                "\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n```")
        try:
            text, _ = self.llm.call(self.mt, self.sys_t, user, self.batch, stage)
            return {int(x["id"]): x.get("fields") or {} for x in parse_json(text).get("items", [])}
        except (ValueError, KeyError, TypeError) as e:
            self.log.append(f"{stage}: JSON hong: {e}")
            return {}

    def apply_changes(self, fields: dict[int, dict], changes: dict[int, dict]) -> dict[int, dict]:
        """Ghep thay doi; muc nao sau khi ghep sinh loi check moi thi giu ban cu."""
        before = self.check_errors()
        new = {i: dict(f) for i, f in fields.items()}
        for i, ch in changes.items():
            if i in new:
                new[i].update({k: v for k, v in ch.items() if k in self.by_id[i]["fields"]})
        self.write_out(new)
        after = self.check_errors()
        for i in changes:
            if len(after.get(i, [])) > len(before.get(i, [])):
                new[i] = fields[i]
                self.log.append(f"#{i}: ban sua sinh loi check moi -> giu ban cu")
        self.write_out(new)
        return new

    # --- cham ---
    def judge(self, fields: dict[int, dict], ids: list[int] | None = None) -> dict[int, dict]:
        sel = [si for si in self.src if ids is None or si["id"] in ids]
        payload = [{"id": si["id"], "source": si["fields"], "translation": fields.get(si["id"], {})} for si in sel]
        user = "Review these translated items.\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n```"
        judges = [(self.mj, False)] + ([(self.mt, True)] if self.low else [])
        merged: dict[int, dict] = {}
        for model, bt in judges:
            for k in range(2):
                try:
                    text, _ = self.llm.call(model, system_judge(self.ws, self.lang, bt), user, self.batch,
                                            "cham-bt" if bt else "cham", max_tokens=16000)
                    got = parse_json(text)
                    break
                except (ValueError, KeyError, TypeError) as e:
                    self.log.append(f"cham: JSON hong lan {k + 1}: {e}")
                    got = None
            if got is None:
                continue
            for x in got.get("items", []):
                try:
                    i = int(x["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                issues = [y for y in x.get("issues") or [] if isinstance(y, dict)]
                merged.setdefault(i, {"id": i, "issues": []})["issues"] += issues
        for i, v in merged.items():
            sev = [y.get("severity") for y in v["issues"]]
            v["score"] = max(0, 100 - sev.count("minor") - 5 * sev.count("major") - 25 * sev.count("critical"))
            v["qa"] = "fix" if ("major" in sev or "critical" in sev) else "ok"
        return merged

    # --- toan bo ---
    def run(self) -> dict:
        fields: dict[int, dict] = {}
        for ch in chunks(self.src, CHUNK_CHARS if self.chunk_chars is None else self.chunk_chars):
            fields.update(self.translate_items(ch))
        missing = [si for si in self.src if si["id"] not in fields]
        if missing:
            self.log.append(f"thieu {len(missing)} muc sau khi dich")
        self.write_out(fields)
        for r in range(MAX_REPAIR):
            errs = {i: e for i, e in self.check_errors().items() if i > 0}
            if not errs:
                break
            redo = [self.by_id[i] for i in errs if not fields.get(i)]
            if redo:
                fields.update(self.translate_items(redo, f"dich-lai{r + 1}"))
                self.write_out(fields)
                errs = {i: e for i, e in self.check_errors().items() if i > 0 and fields.get(i)}
            if errs:
                fields = self.apply_changes(fields, self.revise(fields, errs, f"sua-check{r + 1}", "checker_errors"))
        j = self.judge(fields)
        rounds = 0
        while rounds < MAX_FIX:
            bad = {i: [y for y in v["issues"] if y.get("severity") != "minor"] for i, v in j.items() if v["qa"] == "fix"}
            if not bad:
                break
            rounds += 1
            fields = self.apply_changes(fields, self.revise(fields, bad, f"sua{rounds}", "reviewer_issues"))
            j.update(self.judge(fields, list(bad)))
        return {"batch": self.batch, "judge": self.mj + (f" + {self.mt} (dich nguoc)" if self.low else ""),
                "rounds": rounds, "items": list(j.values()), "note": "; ".join(self.log)[:1500]}


# ---------------- chay ----------------
def load_key(env_path: Path | None) -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for p in [env_path] if env_path else [ROOT / ".env", Path.cwd() / ".env"]:
        if p and p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*(?:export\s+)?(?:BUNPO_)?ANTHROPIC_API_KEY\s*=\s*(.+?)\s*$", line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    return None


def make_client(key: str):
    try:
        import anthropic
    except ImportError:
        sys.exit("Thieu thu vien: pip install anthropic")
    return anthropic.Anthropic(api_key=key, max_retries=8, timeout=900)


def prepare_pilot(ws: Path, pilot: Path, lang: str, batches: list[str]) -> Path:
    for sub in ("source", "glossary", "style", "out", "reports"):
        (pilot / sub).mkdir(parents=True, exist_ok=True)
    for b in batches:
        shutil.copyfile(ws / "source" / f"{b}.json", pilot / "source" / f"{b}.json")
    shutil.copyfile(ws / "glossary" / f"{lang}.json", pilot / "glossary" / f"{lang}.json")
    shutil.copyfile(ws / "style" / f"{lang}.md", pilot / "style" / f"{lang}.md")
    return pilot


def run(args, client=None) -> int:
    ws = workspace(args.ws)
    lang = args.lang
    pilot = Path(args.pilot) if args.pilot else None
    if args.batches:
        batches = [b.strip() for b in args.batches.split(",") if b.strip()]
    elif pilot:
        print("--pilot can --batches"); return 1
    else:
        batches = [r["batch"] for r in tm.todo(tm.load_manifest(ws, lang))][: args.n]
    if not batches:
        print(f"{lang}: khong con lo nao can dich"); return 0
    who = args.who or f"api-{socket.gethostname()}"
    work = prepare_pilot(ws, pilot, lang, batches) if pilot else ws
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    usage = Usage(work / "reports" / lang / "api_usage.csv", args.max_usd)
    if client is None:
        key = load_key(Path(args.env) if args.env else None)
        if not key:
            print("Chua co ANTHROPIC_API_KEY (bien moi truong hoac .env)"); return 1
        client = make_client(key)
    llm = Claude(client, usage)
    if not pilot and not tm.claim(ws, lang, who):
        print(f"BUSY {lang} {tm.lock_holder(ws, lang)}"); return 2
    mlock = threading.Lock()
    reps: list[dict] = []
    stopped = False
    t0 = time.time()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"{lang}: {len(batches)} lo {batches[0]}..{batches[-1]}, song song {args.parallel}"
          + (f", pilot -> {work}" if pilot else ""))

    def one(b: str) -> None:
        nonlocal stopped
        if stopped or usage.over():
            stopped = True
            return
        t = time.time()
        try:
            res = BatchJob(work, lang, b, llm, args.model_translate, args.model_judge, args.chunk_chars, date).run()
        except BudgetExceeded:
            stopped = True
            return
        except Exception as e:  # noqa: BLE001 - mot lo hong khong duoc lam dung ca dot
            res = {"batch": b, "items": [], "note": f"loi: {type(e).__name__}: {str(e)[:300]}"}
        with mlock:
            rep = apply_batch(work, lang, res)
            rep["note"] = res.get("note", "")
            reps.append(rep)
            if not pilot:
                tm.apply_report(ws, {"lang": lang, "batches": [rep]}, who=who)
                tm.claim(ws, lang, who)  # gia han khoa
            print(f"  {b} {rep['status']:7} diem={rep['score']} qa_low={rep['qa_low']} "
                  f"{time.time() - t:.0f}s  tong ${usage.usd:.2f}", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
            list(ex.map(one, batches))
    except KeyboardInterrupt:
        stopped = True
        print("Dung theo yeu cau (lo dang chay do se duoc dich lai lan sau)")
    finally:
        if not pilot:
            tm.release(ws, lang, who)
        reps.sort(key=lambda r: r["batch"])
        rp = work / "reports" / lang / f"api-{stamp}.json"
        note = (f"{who}, {len(reps)} lo, {time.time() - t0:.0f}s, ${usage.usd:.2f}, "
                f"token vao {usage.tokens['in']:,} / ghi cache {usage.tokens['cache_write']:,} / "
                f"doc cache {usage.tokens['cache_read']:,} / ra {usage.tokens['out']:,}")
        write_json(rp, {"lang": lang, "batches": reps, "usd": round(usage.usd, 4), "tokens": usage.tokens})
        write_text(rp.with_suffix(".md"), render_md(lang, reps, note))
        print(note)
        print(f"-> {rp}")
    if stopped and usage.over():
        print(f"Dung vi cham --max-usd {args.max_usd}"); return 3
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lang", choices=LANGS)
    ap.add_argument("--ws", default="translation", help="thu muc translation/ (mac dinh ./translation)")
    ap.add_argument("--n", type=int, default=20, help="so lo toi da (mac dinh 20)")
    ap.add_argument("--batches", help="danh sach lo, vd b002,b050 (bo qua manifest)")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--max-usd", type=float, default=None, help="dung khi tong chi phi cham muc nay")
    ap.add_argument("--pilot", help="thu muc chay thu (khong dung manifest / khoa / out that)")
    ap.add_argument("--who", help="ma khoa (mac dinh api-<ten may>)")
    ap.add_argument("--env", help="duong dan .env chua ANTHROPIC_API_KEY")
    ap.add_argument("--model-translate", default=MODEL_T)
    ap.add_argument("--model-judge", default=MODEL_J)
    ap.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS, help="so ky tu nguon toi da moi yeu cau dich")
    return ap


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
