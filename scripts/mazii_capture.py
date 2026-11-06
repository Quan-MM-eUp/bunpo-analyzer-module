"""D0: ghi du lieu mau that tu API Mazii (de phat trien / test / danh gia ma khong can mang).

    python scripts/mazii_capture.py                       # vi en tw cn ko, cau trong bo cau kiem thu + tu bo sung
    python scripts/mazii_capture.py --langs en,tw --concurrency 2

Chay tren may goi duoc mazii.net, trong thu muc bunpo-analyzer, can .env co BUNPO_MAZII_PEM_PATH
(hoac BUNPO_MAZII_PEM). Ghi tests/fixtures/mazii/<tu dien>.json:
    {"captured": "...", "queries": {"<tu>": <ket qua da giai ma, chi giu truong module dung>}, "errors": [...]}
Chay lai thi bo qua tu da ghi (lam tiep khi bi ngat). Khong in noi dung public.pem.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from bunpo_analyzer.config import Settings
from bunpo_analyzer.core.dictionary.mazii import MAZII_DICTS, decrypt_payload, derive_key, trim_payload
from bunpo_analyzer.core.lookup import dict_queries
from bunpo_analyzer.core.tokenizer import tokenize

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "mazii"
GOLDEN = ROOT / "tests" / "golden" / "golden_set.json"

# Cau bo sung: tu viet kana, cum tu, tu ghep, tu dong am, tinh tu na, tu ngoai lai, tu cap cao.
EXTRA = [
    "富士山に登ったことがありますか。",
    "気をつけてください。",
    "子供たちが猫を見ている。",
    "このケーキはとてもおいしいです。",
    "図書館は静かで、勉強しやすい。",
    "今日は日本語の授業があります。",
    "彼は上手に話せるようになった。",
    "部屋をきれいにしておいてください。",
    "雨が降りそうなので、傘を持っていきます。",
    "その件については検討させていただきます。",
    "物価の上昇に伴い、生活が苦しくなった。",
    "あの方はどなたですか。",
]


def sentences() -> list[str]:
    out = list(EXTRA)
    if GOLDEN.exists():
        out += [x["text"] for x in json.loads(GOLDEN.read_text(encoding="utf-8"))["items"]]
    return list(dict.fromkeys(out))


async def capture(lang: str, queries: list[str], key: bytes, url: str, limit: int, conc: int) -> dict:
    code = MAZII_DICTS[lang]
    path = OUT / f"{code}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"queries": {}}
    todo = [q for q in queries if q not in data["queries"]]
    sem = asyncio.Semaphore(conc)
    lat: list[float] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=10) as http:
        async def one(q: str) -> None:
            async with sem:
                t = time.perf_counter()
                try:
                    r = await http.post(url, json={"dict": code, "query": q, "limit": limit})
                    r.raise_for_status()
                    body = r.json()
                    payload = decrypt_payload(body["encryptedData"], key) if "encryptedData" in body else body
                    data["queries"][q] = trim_payload(payload)
                    lat.append(time.perf_counter() - t)
                except Exception as e:  # noqa: BLE001 - ghi lai, chay tiep
                    errors.append(f"{q}: {type(e).__name__}")

        for k in range(0, len(todo), 50):  # ghi file sau moi 50 tu (lam tiep duoc neu bi ngat)
            await asyncio.gather(*(one(q) for q in todo[k:k + 50]))
            data["captured"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            data["errors"] = errors
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"  {code}: {min(k + 50, len(todo))}/{len(todo)}", flush=True)

    found = sum(1 for q in queries if (data["queries"].get(q) or {}).get("data", {}).get("words"))
    return {"dict": code, "queries": len(queries), "new": len(todo), "errors": len(errors),
            "with_result": found, "p50_ms": round(statistics.median(lat) * 1000) if lat else None,
            "p90_ms": round(sorted(lat)[int(len(lat) * 0.9)] * 1000) if lat else None,
            "kb": round(path.stat().st_size / 1024)}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="vi,en,tw,cn,ko")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    s = Settings()
    pem = s.mazii_pem or Path(s.mazii_pem_path).read_text(encoding="utf-8")
    key = derive_key(pem)
    queries: list[str] = []
    for text in sentences():
        queries += dict_queries(tokenize(text))
    queries = list(dict.fromkeys(queries))
    print(f"{len(sentences())} cau, {len(queries)} tu can tra")
    stats = []
    for lang in [x.strip() for x in a.langs.split(",") if x.strip()]:
        t0 = time.time()
        st = await capture(lang, queries, key, s.mazii_url, s.mazii_limit, a.concurrency)
        st["seconds"] = round(time.time() - t0)
        stats.append(st)
        print(json.dumps(st, ensure_ascii=False))
    (OUT / "capture_report.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = sum(x["errors"] for x in stats)
    print(f"Xong -> {OUT} ({'co ' + str(bad) + ' loi, chay lai de thu lai' if bad else 'khong loi'})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
