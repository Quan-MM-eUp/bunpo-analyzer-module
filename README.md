# bunpo-analyzer

Module phân tích ngữ pháp **một câu tiếng Nhật** cho chatbot Migii AI Sensei. Thiết kế và lộ trình: `../de-xuat-trien-khai-phan-tich-ngu-phap.md` (mục 9, 11), kịch bản: `../kich-ban-module-phan-tich-ngu-phap.md`.

## Cài đặt và chạy test

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                 # bỏ test chạy trên toàn kho (~15 giây): pytest -m "not kho"
```

Cấu hình qua biến môi trường tiền tố `BUNPO_` (chép `.env.example` thành `.env`). `BUNPO_DATA_DIR` trỏ tới thư mục chứa `grammar/`, `word/`, `i18n/` (mặc định thư mục cha, tức `Model bunpo`).

## Cách dùng

```python
from bunpo_analyzer import analyze

result = await analyze("今夜たくさんの宿題がある。", lang="vi")   # AnalysisResult (mục 11.5)
```

## Cấu trúc

```
src/bunpo_analyzer/
├── __init__.py        analyze, AnalysisResult
├── config.py          Settings (BUNPO_*), 16 ngôn ngữ
├── schema.py          khuôn AnalysisResult 1.2 (hợp đồng với app)
├── core/
│   ├── analyzer.py    analyze()                       bước 2.5
│   ├── input_check.py kiểm tra đầu vào, sửa furigana   bước 1.2
│   ├── tokenizer.py   SudachiPy (chế độ C)             bước 1.1
│   ├── data.py        nạp kho, đọc theo lang           bước 1.3
│   ├── lookup.py      tra word_lib                     bước 1.4
│   ├── matcher.py     dò mẫu ngữ pháp                  bước 1.5
│   ├── llm/           base.py + mỗi nhà cung cấp 1 file bước 2.1
│   ├── validator.py   kiểm tra đầu ra LLM              bước 2.3–2.4
│   └── cache.py                                        bước 2.6
├── rules/             luật ngữ pháp *.json (định dạng: đầu `core/matcher.py`)  bước 1.5
├── tables/            particle_table.json: nghĩa trợ từ, trợ động từ, hậu tố (bước 1.4)
└── adapters/chatbot.py                                 giai đoạn 5
tests/
├── fixtures/          2 ví dụ ở mục 11.5
├── golden/
│   ├── golden_set.json   bộ câu kiểm thử (76 câu, 20 câu có đáp án đầy đủ)
│   ├── render_review.py  tạo REVIEW.md cho người duyệt
│   └── REVIEW.md
├── test_golden_set.py    kiểm tra bộ câu tự nhất quán, id mẫu có trong kho
└── test_skeleton.py
```

Không có adapter render: app tự dựng giao diện từ `AnalysisResult`.

## Tiến độ

| Bước | Trạng thái |
|---|---|
| 0.1 Khung package | Xong |
| 0.2 Bộ câu kiểm thử | Bản nháp, chờ duyệt (`tests/golden/REVIEW.md`) |
| 1.1 Tách từ | Xong (SudachiPy thay Lindera, xem đầu `core/tokenizer.py`) |
| 1.2 Kiểm tra đầu vào | Xong (`core/input_check.py`) |
| 1.3 Nạp kho | Xong (`core/data.py`) |
| 1.4 Tra từ | Xong (`core/lookup.py`, bảng trợ từ `tables/particle_table.json` - bản nháp, cần duyệt) |
| 1.5a Bộ máy dò mẫu ngữ pháp | Xong (`core/matcher.py`) |
| 1.5b Luật N5 | Xong, bản nháp chờ duyệt: 228 luật + 4 mẫu để LLM (`rules/n5.json`, bản đọc duyệt `docs/rules_N5.md`) |

## Bộ câu kiểm thử

- Câu có đáp án đầy đủ: mỗi dòng ghi phần câu bằng **chữ** (không dùng số thứ tự token) để không phụ thuộc bộ tách từ.
- `grammar_must`: mẫu bắt buộc phải nhận ra; phần tử là mảng nghĩa là **một trong các id** đều đúng (kho có mẫu trùng nhau). `grammar_ok`: nhận thêm không bị trừ điểm.
- Sửa `golden_set.json` xong thì chạy `python tests/golden/render_review.py` để cập nhật `REVIEW.md`.

## Kho dữ liệu và bản dịch

`BUNPO_DATA_DIR` trỏ tới thư mục có `word/word_lib.json`, `grammar/grammar_lib.json`, `i18n/*.json`. Bản dịch (khi có) đặt cạnh kho gốc, theo `id`:

```
word/word_text.en.json        {"1": {"meaning": "movie, film"}}
grammar/grammar_text.en.json  {"245": {"name": "...", "meaning": "...", "explain": "...", "mistakes": "..."}}
```

Thiếu file, thiếu `id` hoặc thiếu trường thì dùng tiếng Việt. Âm Hán Việt chỉ trả cho tiếng Việt. `Kho.version` là mã băm nội dung các file đã nạp (đổi kho là đổi khóa cache).

## Luật dò mẫu ngữ pháp

Mỗi file trong `src/bunpo_analyzer/rules/` chứa danh sách luật; mỗi luật có `id` (khớp `grammar_lib`), `patterns` (chuỗi điều kiện cho từng token), `examples` và `not_examples`. Hai danh sách ví dụ được test tự động, nên viết luật mới chỉ cần thêm ví dụ là có kiểm thử. Mô tả đầy đủ các điều kiện ở đầu `core/matcher.py`. Mẫu không viết được luật thì ghi vào `llm_only` (kèm lý do).

- Thử một file luật (ví dụ khớp, độ phủ trên câu ví dụ của kho, độ rộng): `python scripts/try_rules.py src/bunpo_analyzer/rules/n5.json --data ..`
- Xem cách tách từ của một câu: `python scripts/try_rules.py --show "文"`
- Tạo bản đọc duyệt: `python scripts/rules_review.py src/bunpo_analyzer/rules/n5.json > docs/rules_N5.md`
