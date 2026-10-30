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
├── __init__.py        analyze, grammar_detail, AnalysisResult
├── config.py          Settings (BUNPO_*), 16 ngôn ngữ
├── schema.py          khuôn AnalysisResult 1.3 (hợp đồng với app)
├── core/
│   ├── analyzer.py    analyze(), analyze_full() (kèm log) bước 2.5
│   ├── assemble.py    ghép AnalysisResult đầy đủ      bước 2.5
│   ├── input_check.py kiểm tra đầu vào, sửa furigana   bước 1.2
│   ├── tokenizer.py   SudachiPy (chế độ C)             bước 1.1
│   ├── data.py        nạp kho, đọc theo lang           bước 1.3
│   ├── lookup.py      tra word_lib                     bước 1.4
│   ├── matcher.py     dò mẫu ngữ pháp                  bước 1.5
│   ├── llm/           base.py + mỗi nhà cung cấp 1 file bước 2.1
│   ├── validator.py   kiểm tra đầu ra LLM              bước 2.3–2.4
│   ├── translate.py   "dịch nhẹ" phần chữ sang ngôn ngữ khác bước 2.6
│   ├── canon.py       mẫu trùng -> mẫu chuẩn           bước 3.2
│   ├── grammar_meta.py nhãn ngắn, "Dễ nhầm với"        bước 4.1
│   ├── grammar_detail.py dữ liệu bảng ngữ pháp        bước 4.2
│   └── cache.py       cache (memory / redis)           bước 2.6
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
| 1.5c Luật N4 | Xong, bản nháp chờ duyệt: 295 luật + 4 mẫu để LLM (`rules/n4.json`, `docs/rules_N4.md`) |
| 1.5d Luật N3–N1 | Xong, bản nháp chờ duyệt: N3 407 + 1 để LLM, N2 336, N1 346 (`rules/n3.json`, `n2.json`, `n1.json`, `docs/rules_N3/N2/N1.md`) |
| 2.1 Lớp gọi LLM | Xong (`core/llm/`; OpenAI qua gateway nội bộ; tạm chọn `gpt-5-mini` suy nghĩ thấp, dự phòng `gpt-4.1`) |
| 2.2 Prompt + khuôn đầu ra | Xong (prompt bản 5: LLM chia câu theo cụm `core/chunker.py`) |
| 2.3 Kiểm tra bằng code + gọi lại | Xong (`core/validator.py`, `pipeline.analyze_llm`) |
| 2.4 Câu sai / nghi sai | Xong (`core/grammar_check.py`: `correction_at`, kiểm lại `at`); chạy thật 10/10 câu thử đúng (30/10) |
| 2.5 Ghép kết quả | Xong (`core/assemble.py`; `analyze()` dùng được; `scripts/replay_assemble.py` ghép lại từ file `runs/`) |
| 2.6 Cache + dịch nhẹ | Xong (`core/cache.py`, `core/translate.py`); chạy thật 30/10: vi/en/ko đúng, trúng cache khoảng 10 ms, dịch nhẹ khoảng 1,5 s, $0,0004 |
| 3.1 Chấm tự động | Xong (`scripts/eval.py`, `evaluation.py`); lần chạy 30/10 (gpt-5-mini / gpt-4.1) ghi ở mục 9 file kế hoạch |
| 3.2 Sửa theo lỗi | Xong 3 lượt: tự vá lỗi khuôn, prompt bản 9, gom mẫu trùng (`core/canon.py`, `docs/mau_trung.md`), mẫu nền chỉ gắn khi câu không có mẫu khác, kiểm tra ngôn ngữ phần giải thích lỗi, lỗi hết ngân sách gateway không gọi lại; chốt 30/10: dòng đúng 99%, nhóm 100%, đạt khuôn lần đầu 90% |
| 4.1 Nhãn ngắn, "Dễ nhầm với" | Xong (`core/grammar_meta.py`, `tables/grammar_meta.json`, sinh bằng `scripts/build_grammar_meta.py`; soát ở `docs/grammar_meta_review.md`) |
| 4.2 Dữ liệu bảng ngữ pháp | Xong (`core/grammar_detail.py`: `grammar_detail(id, lang)`; soát bằng `scripts/check_grammar_detail.py` → `docs/grammar_detail_review.md`) |

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

## Gọi LLM

Chép `.env.example` thành `.env`, điền `BUNPO_OPENAI_API_KEY` (file `.env` đã nằm trong `.gitignore`, không bị đẩy lên GitHub). Đổi model / nhà cung cấp chỉ cần sửa `.env`.

- Kiểm tra kết nối: `python scripts/llm_smoke.py` (thêm `--models` để xem gateway cho phép model nào).
- Test gọi thật: `pytest -m live`. Mặc định `pytest` không gọi mạng.
- Thử prompt phân tích: `python scripts/try_prompt.py` (3 câu artifact), `--golden` (20 câu có đáp án), `--errors` (câu sai / nghi sai), `--text "..."`, `--model gpt-4.1`. Kết quả in ra màn hình và lưu vào `runs/` (không đẩy lên GitHub). Chấm so với đáp án: `python scripts/score_run.py runs/<file>.json`.
- Ghép lại kết quả đầy đủ từ một file đã chạy (không gọi LLM): `python scripts/replay_assemble.py runs/<file>.json [G02]`.
- Chấm tự động (bước 3.1): `python scripts/eval.py` (bộ câu kiểm thử + 20 câu ví dụ kho mỗi cấp N5–N3, gọi qua `analyze_full` thật, không cache). So sánh model: `--models gpt-5-mini gpt-4.1`. Báo cáo `runs/eval_<thời gian>.md`, từng câu ở file JSON cùng tên. Chỉ đo bộ luật (không gọi LLM): `--rules-only --levels N5 N4 N3 N2 N1`, câu luật bỏ sót ghi vào `runs/rules_miss_<cấp>.txt`.
- Gom mẫu trùng: `python scripts/build_canon.py` (sinh lại `tables/grammar_canon.json` và `docs/mau_trung.md` khi kho hoặc luật đổi; bảng sửa tay được).
- Thử cache + dịch nhẹ: `python scripts/try_cache.py` (mỗi câu chạy lần lượt vi, vi, en, ko, en; in trạng thái cache, độ trễ, chi phí).

## Cache

`analyze()` tự dùng cache (`BUNPO_CACHE_BACKEND`: `memory` mặc định, `redis` cho nhiều worker, `none` để tắt).

- Khóa gồm câu đã chuẩn hoá, phiên bản khuôn, prompt, kho gốc (`word_lib` + `grammar_lib`), bộ luật, từ điển tách từ và tên model chính. Đổi bất kỳ thứ nào thì khóa đổi theo, mục cũ tự hết hạn, không cần xoá tay.
- Lưu đầu ra LLM đã kiểm tra, không lưu kết quả cuối: nghĩa từ, nghĩa mẫu lấy lại từ kho mỗi lần, nên sửa kho hay thêm bản dịch kho là hiện ngay.
- Cùng câu, ngôn ngữ khác: giữ cấu trúc, chỉ gọi model rẻ (`BUNPO_LLM_LIGHT_MODEL`) dịch bản dịch câu, nghĩa từng dòng, lý do / giải thích lỗi. Dịch nhẹ hỏng thì phân tích lại đầy đủ.
- Chỉ lưu câu phân tích được (kể cả câu sai ngữ pháp). Lỗi LLM không lưu để lần sau thử lại. Cache hỏng (Redis mất kết nối) thì bỏ qua, vẫn phân tích bình thường.
