"""Kiem tra dau ra LLM bang code (buoc 2.3, muc 3.5 file ke hoach).

Dau vao la dau ra da doi sang vi tri TOKEN (postprocess.to_token_positions).
Chia 2 loai:
- Loi nang (errors): cau truc khong dung duoc -> goi lai model manh hon kem
  danh sach loi; van loi -> structure_failed.
- Tu sua (fixes): sai nho, code sua duoc ma khong can goi lai (mau ngoai danh
  sach ung vien, nhieu mau trong cung mot nhom vi tri, thieu co main...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bunpo_analyzer.core.llm_output import LLMNode, LLMOutput
from bunpo_analyzer.core.matcher import Match
from bunpo_analyzer.core.tokenizer import MorphToken


@dataclass
class Report:
    output: Optional[LLMOutput]  # da tu sua (neu khong co loi nang)
    errors: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _span_ok(span: Optional[list[int]], n_tok: int) -> bool:
    return bool(span) and len(span) == 2 and 0 <= span[0] < span[1] <= n_tok


def group_token_span(nodes: list[LLMNode], gid: str) -> Optional[tuple[int, int]]:
    """Pham vi token cua nhom = tu dong con dau den dong con cuoi (ke ca nhom long)."""
    kids: dict[Optional[str], list[LLMNode]] = {}
    for n in nodes:
        kids.setdefault(n.parent, []).append(n)
    spans: list[tuple[int, int]] = []
    stack = [gid]
    seen = set()
    while stack:
        g = stack.pop()
        if g in seen:
            break
        seen.add(g)
        for c in kids.get(g, []):
            if c.type == "group":
                stack.append(c.id)
            elif c.span:
                spans.append((c.span[0], c.span[1]))
    if not spans:
        return None
    return min(s for s, _ in spans), max(e for _, e in spans)


# ---------------- tu va loi khuon nho (buoc 3.2) ----------------
# Lan chay 3.1: ~10% cau sai khuon o lan dau, phan lon la loi nho: sot 1 cum, 2 dong chong
# 1 token, dong an co span, parent tro vao dong, main dat sai cap. Code sua duoc thi khong
# phai goi lai model du phong (them 3-10 s).
_MAX_GAP = 3
_TIME_NOUNS = frozenset("今日 きょう 明日 あした あす 昨日 きのう 今 いま 今年 去年 来年 今月 先月 来月 今週 先週 来週 "
                        "毎日 毎朝 毎晩 毎週 毎月 毎年 今朝 けさ 今夜 今晩 朝 夜 昼 夕方 週末 最近 昔 将来 午前 午後 "
                        "週末 夏 冬 春 秋 夏休み 冬休み 春休み".split())
# Danh tu noi menh de voi phan sau: thuoc menh de dung truoc (giong ために o chunker).
_CLAUSE_NOUNS = frozenset("間 あいだ 時 とき ため 為 前 後 あと うち まま 場合 ところ 途中 際 度 たび 以上 代わり かわり "
                          "通り とおり 限り かぎり くせ せい おかげ 結果".split())  # chi va cho trong ngan (so token); dai hon la LLM chia sai, de goi lai


def _gap_target(toks: list[MorphToken], run: list[int], prev: Optional[dict], nxt: Optional[dict]) -> Optional[dict]:
    """Dong nen nhan phan sot, hoac None neu phan sot la ca mot thanh phan (ケーキは, 磨きます):
    khi do LLM chia sai that, de goi lai model du phong.

    - Bat dau bang tro tu / tro dong tu / danh tu hinh thuc / dong tu phu (ときは, 間に, ものの,
      につれて, ともなって) -> dong truoc.
    - Dong truoc ket thuc bang tu bo nghia (この, 私の) -> dong truoc (この + 魚).
    - Phan sot chi la tu bo nghia (いい, 大きな, とても) -> dong sau (いい + 風が).
    """
    first, last = toks[run[0]], toks[run[-1]]
    pd = first.pos_detail
    if prev is not None:
        if first.pos in ("prt", "aux") or (len(pd) > 1 and pd[1] in ("非自立可能", "助動詞語幹")):
            return prev
        if first.base in _CLAUSE_NOUNS or first.surface in _CLAUSE_NOUNS:
            return prev  # 遊んでいる + 間に, 帰る + ときは
        pl = toks[prev["span"][1] - 1]
        if (pl.pos_detail and pl.pos_detail[0] in ("連体詞", "接頭辞")) or (pl.pos == "prt" and pl.surface == "の"):
            return prev
    if nxt is not None:
        lpd = last.pos_detail
        modifier = (last.pos == "adv" or (lpd and lpd[0] == "連体詞")
                    or (last.pos == "adj" and (last.cform or "").startswith("連体形"))
                    or (last.pos == "prt" and last.surface in ("の", "な")))
        if modifier:
            return nxt
    return None


def repair(out: LLMOutput, toks: list[MorphToken]) -> tuple[LLMOutput, list[str]]:
    """Sua loi khuon nho truoc khi kiem tra. Vi tri theo TOKEN."""
    if out.input_check.status == "error" or not out.nodes:
        return out, []
    fixes: list[str] = []
    d = out.model_dump()
    nodes = d["nodes"]
    n_tok = len(toks)
    by_id = {n["id"]: n for n in nodes}
    rows = [n for n in nodes if n["type"] == "row"]

    # parent tro vao mot dong -> dua len nhom cua dong do
    for n in nodes:
        p = by_id.get(n["parent"]) if n["parent"] else None
        if p is not None and p["type"] == "row":
            n["parent"] = p["parent"]
            fixes.append(f"{n['id']}: parent {p['id']} la dong -> {p['parent']}")

    def owners() -> dict[int, dict]:
        own: dict[int, dict] = {}
        for r in rows:
            if not r["hidden"] and _span_ok(r["span"], n_tok):
                for i in range(*r["span"]):
                    own.setdefault(i, r)
        return own

    # dong an co span: phan do da co dong khac -> bo span; chua co -> thanh dong thuong
    for r in rows:
        if r["hidden"] and r["span"] is not None:
            own = owners()
            if _span_ok(r["span"], n_tok) and all(i not in own for i in range(*r["span"])):
                r["hidden"], r["jp"] = False, None
                fixes.append(f"{r['id']}: dong an co span chua ai giu -> dong thuong")
            else:
                r["span"] = None
                fixes.append(f"{r['id']}: bo span cua dong an")

    # 2 dong chong nhau: dong bat dau sau lui diem bat dau ve sau dong truoc
    vis = sorted((r for r in rows if not r["hidden"] and _span_ok(r["span"], n_tok)), key=lambda r: r["span"][0])
    for a, b in zip(vis, vis[1:]):
        if b["span"][0] < a["span"][1] < b["span"][1] and a["span"][0] < b["span"][0]:
            b["span"] = [a["span"][1], b["span"][1]]
            fixes.append(f"{b['id']}: bo phan chong voi {a['id']}")

    # cum sot (ngan) -> ghep vao dong ben canh
    own = owners()
    k = 0
    while k < n_tok:
        if k in own or toks[k].pos == "punct":
            k += 1
            continue
        j = k
        while j < n_tok and j not in own and toks[j].pos != "punct":
            j += 1
        run = list(range(k, j))
        prev = own.get(k - 1)
        nxt = own.get(j)
        tgt = _gap_target(toks, run, prev, nxt) if len(run) <= _MAX_GAP else None
        if tgt is not None:
            if tgt is prev:
                tgt["span"] = [tgt["span"][0], j]
            else:
                tgt["span"] = [k, tgt["span"][1]]
            fixes.append(f"{tgt['id']}: them phan sot {''.join(toks[i].surface for i in run)}")
            own = owners()
        k = j

    # vai tro theo tro tu cuoi dong (quy tac trong prompt; LLM hay lech o vai cho hay gap)
    for r in rows:
        if r["hidden"] or not _span_ok(r["span"], n_tok):
            continue
        seg = [t for t in toks[r["span"][0]:r["span"][1]] if t.pos != "punct"]
        if not seg:
            continue
        last = seg[-1]
        case = last.pos == "prt" and len(last.pos_detail) > 1 and last.pos_detail[1] == "格助詞"
        new = None
        if case and last.surface == "を" and r["role"] not in ("object", "predicate"):
            new = "object"  # 音楽を (adv_manner) -> object
        elif case and last.surface in ("へ", "に") and r["role"] == "adv_place" and len(seg) == 2 \
                and seg[0].pos == "noun" and seg[0].base not in _TIME_NOUNS:
            new = "complement"  # 駅に, 日本へ: diem den
        elif r["role"] == "topic" and len(seg) == 2 and last.surface in ("は", "も") and seg[0].base in _TIME_NOUNS:
            new = "adv_time"  # 今日は, 明日は
        if new:
            fixes.append(f"{r['id']}: role {r['role']} -> {new} (theo tro tu {last.surface})")
            r["role"] = new

    # nhom khong co dong predicate nhung dong cuoi cua nhom co dong tu / tinh tu / tro dong tu
    # (LLM hay gan nham role adv_reason, adv_time cho 約束したから, なれば): doi thanh predicate
    for g in nodes:
        if g["type"] != "group":
            continue
        kids = [n for n in nodes if n["parent"] == g["id"]]
        if any(k["type"] == "group" or k["role"] == "predicate" for k in kids):
            continue
        vis = [k for k in kids if k["type"] == "row" and not k["hidden"] and _span_ok(k["span"], n_tok)]
        if vis:
            last = max(vis, key=lambda k: k["span"][0])
            if any(t.pos in ("verb", "adj", "aux") for t in toks[last["span"][0]:last["span"][1]]):
                fixes.append(f"{last['id']}: role {last['role']} -> predicate (vi ngu cua nhom {g['id']})")
                last["role"] = "predicate"

    # vi ngu chinh: dung 1 dong predicate ngoai cung
    top_preds = [r for r in rows if r["parent"] is None and r["role"] == "predicate"]
    mains = [r for r in rows if r["main"]]
    bad_main = len(mains) != 1 or mains[0]["parent"] is not None or mains[0]["role"] != "predicate"
    if bad_main and top_preds:
        last = max(top_preds, key=lambda r: (r["span"] or [0])[0])  # tieng Nhat: vi ngu chinh o cuoi
        for r in rows:
            r["main"] = r is last
        fixes.append(f"{last['id']}: dat main (vi ngu ngoai cung cuoi cau)")
    return LLMOutput.model_validate(d), fixes


# Mau "nen" xuat hien trong gan nhu moi cau: chi gan khi cau khong co mau nao khac, de
# the ngu phap khong che mat mau chinh. #34 Vます/ません/ました, #12 NをV, #15 N2のN1,
# #3 このN/そのN/あのN, #76 NがV.
BACKGROUND_IDS = frozenset({34, 12, 15, 3, 76})
# Tro tu co ban va です: prompt dan LLM chi gan khi la diem chinh cua cau.
BASIC_PARTICLE_IDS = frozenset({17, 18, 19, 20, 21, 22, 23, 25, 32, 315})

_SPLIT_PRT = frozenset({"が", "を", "へ"})
# Thanh ngu: danh tu + が/を + dong tu la mot vi ngu (気がする, ことがある, 仕方がない)
_IDIOM_NOUNS = frozenset({"気", "こと", "事", "仕方", "しかた", "しょう", "手", "声", "音", "味", "匂い", "におい"})


def _merged_row(toks: list[MorphToken], span: list[int]) -> Optional[str]:
    """Dong co が/を/へ o giua roi den dong tu / tinh tu: LLM gop ca menh de (日本へ行くために)."""
    seg = toks[span[0]:span[1]]
    for k, t in enumerate(seg[:-1]):
        if t.surface in _SPLIT_PRT and t.pos == "prt" and len(t.pos_detail) > 1 and t.pos_detail[1] == "格助詞":
            if k > 0 and (seg[k - 1].base in _IDIOM_NOUNS or seg[k - 1].surface in _IDIOM_NOUNS):
                continue
            if any(x.pos in ("verb", "adj") for x in seg[k + 1:]):
                return "".join(x.surface for x in seg[:k + 1])
    return None


def validate(out: LLMOutput, toks: list[MorphToken], matches: list[Match], text: str,
             pos_errors: Optional[list[str]] = None, lang: str = "vi") -> Report:
    errors: list[str] = list(pos_errors or [])
    fixes: list[str] = []
    d = out.model_dump()
    ic = d["input_check"]
    n_tok = len(toks)

    # --- 6. input_check ---
    # explain / reason hien cho nguoi hoc: phai viet bang ngon ngu cua ho, khong phai tieng Nhat
    from bunpo_analyzer.core.translate import jp_ratio

    for k in ("explain", "reason"):
        if ic[k] and jp_ratio(ic[k], lang) > 0.5:
            errors.append(f"input_check {k} phai viet bang ngon ngu nguoi dung, khong viet bang tieng Nhat")
    if ic["status"] == "error":
        for k in ("at", "explain", "correction"):
            if not ic[k]:
                errors.append(f"input_check error: thieu {k}")
        if ic["at"] is not None and not _span_ok(ic["at"], n_tok):
            errors.append("input_check error: at khong hop le")
        if ic["correction"] and ic["correction"].strip() == text.strip():
            errors.append("input_check error: correction giong het cau goc")
        if d["nodes"]:
            d["nodes"] = []
            fixes.append("status error: bo nodes")
        d["translation"] = None
        return Report(LLMOutput.model_validate(d) if not errors else None, errors, fixes)
    if ic["status"] == "suspect" and not _span_ok(ic["at"], n_tok):
        ic["at"] = None  # van hien phan tich, chi bo vi tri canh bao
        fixes.append("suspect: bo at khong hop le")
    if not d["translation"]:
        errors.append("thieu translation")
    nodes = [LLMNode.model_validate(n) for n in d["nodes"]]
    if not nodes:
        errors.append("nodes rong")
        return Report(None, errors, fixes)

    # --- 2. id, parent, vong lap ---
    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append("trung id node")
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        if n.parent is not None:
            p = by_id.get(n.parent)
            if p is None or p.type != "group":
                errors.append(f"{n.id}: parent {n.parent} khong phai nhom co that")
        hops, cur = 0, n
        while cur is not None and cur.parent is not None and hops <= len(nodes):
            cur, hops = by_id.get(cur.parent), hops + 1
        if hops > len(nodes):
            errors.append(f"{n.id}: vong lap parent")
    for n in nodes:
        if n.type == "row":
            if n.role is None:
                errors.append(f"{n.id}: dong thieu role")
            if n.hidden:
                if n.span is not None:
                    errors.append(f"{n.id}: dong an khong duoc co span")
                if not n.jp:
                    errors.append(f"{n.id}: dong an thieu jp")
            elif not _span_ok(n.span, n_tok):
                errors.append(f"{n.id}: span {n.span} khong hop le")
        else:
            if n.kind is None:
                errors.append(f"{n.id}: nhom thieu kind")
            if group_token_span(nodes, n.id) is None:
                errors.append(f"{n.id}: nhom khong co dong con")

    # --- 1. phu kin token, khong chong nhau ---
    rows = [n for n in nodes if n.type == "row" and not n.hidden and _span_ok(n.span, n_tok)]
    owner: dict[int, str] = {}
    for r in rows:
        for i in range(r.span[0], r.span[1]):
            if i in owner:
                errors.append(f"token {i} ({toks[i].surface}) nam trong ca {owner[i]} va {r.id}")
            owner[i] = r.id
    missing = [t for t in toks if t.pos != "punct" and t.i not in owner]
    if missing:
        errors.append("token khong thuoc dong nao: " + "".join(t.surface for t in missing))

    # --- 3. dung 1 vi ngu chinh o cap ngoai cung ---
    mains = [n for n in nodes if n.type == "row" and n.main]
    if not mains:
        top_preds = [n for n in nodes if n.type == "row" and n.parent is None and n.role == "predicate"]
        if len(top_preds) == 1:
            top_preds[0].main = True
            fixes.append(f"{top_preds[0].id}: dat main")
        else:
            errors.append("khong co vi ngu chinh (main)")
    elif len(mains) > 1:
        errors.append("nhieu hon 1 vi ngu chinh (main)")
    elif mains[0].parent is not None or mains[0].role != "predicate":
        errors.append(f"{mains[0].id}: vi ngu chinh phai la predicate o cap ngoai cung")

    # --- 3b. moi nhom co vi ngu rieng; dong khong gop nhieu thanh phan (buoc 3.2) ---
    for n in nodes:
        if n.type == "group" and not any(c.parent == n.id and (c.type == "group" or c.role == "predicate")
                                          for c in nodes):
            errors.append(f"{n.id}: nhom khong co dong vi ngu rieng (tach vi ngu cua menh de thanh dong predicate)")
    for r in rows:
        merged = _merged_row(toks, r.span)
        if merged:
            errors.append(f"{r.id}: dong gop nhieu thanh phan, tach sau {merged}")

    # --- 5. nhom rel dung ngay truoc danh tu duoc bo nghia ---
    for n in nodes:
        if n.type == "group" and n.kind == "rel":
            gs = group_token_span(nodes, n.id)
            if n.head is None or not 0 <= n.head < n_tok:
                errors.append(f"{n.id}: nhom rel thieu head")
            elif gs and gs[1] != n.head:
                between = toks[gs[1]:n.head] if gs[1] < n.head else []
                if gs[1] > n.head or any(t.pos != "punct" for t in between):
                    # head la token dau cua cum danh tu; cum co the bat dau bang tu bo nghia
                    head_ok = gs[1] <= n.head and all(t.pos in ("noun", "adj") for t in between)
                    if not head_ok:
                        errors.append(f"{n.id}: nhom rel khong dung ngay truoc {toks[n.head].surface}")

    # --- 4. mau ngu phap: chi trong ung vien; moi nhom vi tri toi da 1 id (tu sua) ---
    starts: dict[int, list[int]] = {}
    for m in matches:
        starts.setdefault(m.grammar_id, []).append(m.core_start)
    used_groups: set[int] = set()
    for n in nodes:
        rng = (n.span[0], n.span[1]) if n.type == "row" and _span_ok(n.span, n_tok) else group_token_span(nodes, n.id)
        keep = []
        for g in n.grammar:
            if g not in starts:
                fixes.append(f"{n.id}: bo mau {g} ngoai danh sach ung vien")
                continue
            inside = [s0 for s0 in starts[g] if rng and rng[0] <= s0 < rng[1]]
            grp = (inside or starts[g])[0]  # nhom vi tri cua mau nay tai node nay
            if grp in used_groups:
                fixes.append(f"{n.id}: bo mau {g} trung nhom vi tri")
                continue
            used_groups.add(grp)
            keep.append(g)
        n.grammar = keep

    # --- 4b. mau nen chi gan khi cau khong co mau nao khac (buoc 3.2) ---
    all_ids = {g for n in nodes for g in n.grammar}
    if all_ids - BACKGROUND_IDS - BASIC_PARTICLE_IDS and all_ids & BACKGROUND_IDS:
        for n in nodes:
            drop = [g for g in n.grammar if g in BACKGROUND_IDS]
            if drop:
                n.grammar = [g for g in n.grammar if g not in BACKGROUND_IDS]
                fixes.append(f"{n.id}: bo mau nen {drop} (cau da co mau khac)")

    if errors:
        return Report(None, errors, fixes)
    d["nodes"] = [n.model_dump() for n in nodes]
    return Report(LLMOutput.model_validate(d), errors, fixes)
