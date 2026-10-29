"""Tao file REVIEW.md tu golden_set.json de nguoi duyet doc.

Chay: python tests/golden/render_review.py [duong/dan/grammar_lib.json]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROLE = {"subject": "Chủ ngữ", "topic": "Chủ đề", "object": "Tân ngữ", "complement": "Bổ ngữ",
        "predicate": "Vị ngữ", "adv_time": "TN thời gian", "adv_place": "TN nơi chốn",
        "adv_manner": "TN cách thức", "adv_reason": "TN lý do"}
KIND = {"rel": "Mệnh đề bổ nghĩa", "sub": "Vế phụ", "quote": "Trích dẫn", "nominal": "Danh từ hoá"}


def main():
    data = json.loads((HERE / "golden_set.json").read_text(encoding="utf-8"))
    lib_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[2] / "grammar" / "grammar_lib.json"
    lib = {}
    if lib_path.exists():
        lib = {int(g["id"]): f"{g['grammar']} ({g['level']})" for g in json.loads(lib_path.read_text(encoding="utf-8"))}

    def gname(ids):
        out = []
        for x in ids:
            alt = x if isinstance(x, list) else [x]
            out.append(" hoặc ".join(f"#{i} {lib.get(i, '?')}" for i in alt))
        return "; ".join(out) or "—"

    def tree(nodes, depth=0):
        lines = []
        pad = "  " * depth
        for n in nodes:
            if "group" in n:
                head = f" cho {n['head']}" if n.get("head") else ""
                g = f" · {gname(n['grammar'])}" if n.get("grammar") else ""
                lines.append(f"{pad}- **[{KIND[n['group']]}{head}]** {n['text']}{g}")
                lines += tree(n["children"], depth + 1)
            else:
                role = "Vị ngữ chính" if n.get("main") else ROLE[n["role"]]
                if n.get("hidden"):
                    role += " (ẩn)"
                jp = n.get("jp") or n["text"]
                g = f" · {gname(n['grammar'])}" if n.get("grammar") else ""
                lines.append(f"{pad}- {role}: {jp} — {n['gloss']}{g}")
        return lines

    out = ["# Duyệt bộ câu kiểm thử (bước 0.2)", "",
           f"Phiên bản {data['version']} · {len(data['items'])} câu. Sửa trực tiếp trong `golden_set.json` "
           "rồi chạy lại script này. Duyệt xong câu nào thì đổi `status` thành `approved`.", "",
           "## Phần A: 20 câu có đáp án đầy đủ (cần duyệt kỹ)", ""]
    for it in data["items"]:
        if "full" not in it["tags"]:
            continue
        e = it["expect"]
        out += [f"### {it['id']} · {it['level']} · {it['text']}", "",
                f"Dịch tham khảo: {e['translation']}", ""] + tree(e["structure"]) + [
                "", f"- Mẫu bắt buộc: {gname(e['grammar_must'])}",
                f"- Mẫu chấp nhận thêm: {gname(e['grammar_ok'])}"]
        if it.get("note"):
            out.append(f"- **Ghi chú:** {it['note']}")
        out.append("")
    out += ["## Phần B: các câu còn lại (duyệt nhanh)", "",
            "| ID | Kịch bản | Câu | Kết quả mong đợi | Ghi chú |", "|---|---|---|---|---|"]
    for it in data["items"]:
        if "full" in it["tags"]:
            continue
        e = it["expect"]
        if e.get("error"):
            exp = e["error"]["code"] + (f": {e['error']['reason']}" if e["error"].get("reason") else "")
            if e.get("correction"):
                exp += f" → {e['correction']}"
        elif e.get("auto_fix"):
            exp = f"tự sửa → {e['auto_fix']}"
        else:
            st = e["input_check"] if isinstance(e["input_check"], str) else " / ".join(e["input_check"])
            exp = f"input_check = {st}"
            if e.get("grammar_must"):
                exp += f"; mẫu: {gname(e['grammar_must'])}"
        text = it["text"] if len(it["text"]) <= 40 else it["text"][:40] + "…"
        out.append(f"| {it['id']} | {it['case']} | {text} | {exp} | {it.get('note', '')} |")
    (HERE / "REVIEW.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("Da ghi", HERE / "REVIEW.md")


if __name__ == "__main__":
    main()
