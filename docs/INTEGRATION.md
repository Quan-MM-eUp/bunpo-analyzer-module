# Tích hợp bunpo-analyzer vào chatbot Migii AI Sensei

Tài liệu dành cho người (hoặc Claude) tích hợp module vào chatbot. Đọc xong tài liệu này là đủ để tích hợp, không cần đọc code module. Phiên bản module **0.2.1**, khuôn kết quả **1.5**.

Đi kèm (cùng repo, cùng thư mục `docs/`): `docs/schema/*.schema.json` (JSON Schema sinh từ code) và `docs/examples/*.json` (kết quả chạy thật, dùng làm dữ liệu giả cho app). Mọi thứ cần để tích hợp đều có ở đây; các file khác chỉ để tham khảo thêm: `CHANGELOG.md`, thiết kế gốc mục 11–12 file `de-xuat-trien-khai-phan-tich-ngu-phap.md`, kịch bản hội thoại `kich-ban-module-phan-tich-ngu-phap.md`.

## Mục lục

1. Module làm gì
2. Cài đặt
3. Cấu hình và dữ liệu cần triển khai
4. API công khai
5. Khuôn kết quả `AnalysisResult`
6. Bảng ngữ pháp `GrammarDetail`
7. Nhãn giao diện `labels()`
8. Xử lý từng trường hợp (câu đúng, nghi sai, sai, tự sửa, đầu vào lỗi, lỗi AI)
9. Ngôn ngữ
10. Hiệu năng, chi phí, chạy đồng thời
11. Tích hợp vào chatbot hiện tại (từng bước)
12. Hạn chế đã biết
13. Câu hỏi thường gặp

---

## 1. Module làm gì

Nhận **đúng một câu tiếng Nhật** và ngôn ngữ người dùng, trả về một JSON (`AnalysisResult`) đủ để app dựng màn hình phân tích:

- Tách từ, cách đọc (furigana), từ loại, nghĩa từng từ khi bấm vào.
- Bản dịch cả câu.
- Cấu trúc câu: các dòng (chủ ngữ, vị ngữ, tân ngữ…) và nhóm mệnh đề lồng nhau.
- Mẫu ngữ pháp có trong câu, kèm cấp JLPT (id khớp kho `grammar_lib`).
- Kiểm tra câu: đúng / có thể chưa tự nhiên / sai ngữ pháp (khi sai: chỗ sai, giải thích, câu đúng).

Thêm hai hàm phụ không gọi AI: `grammar_detail(id, lang)` cho bảng thông tin một mẫu ngữ pháp, `labels(lang)` cho chữ hiển thị của các mã trong kết quả.

Module **không** dựng giao diện, **không** lưu kết quả theo người dùng, **không** trừ lượt hỏi. Những việc đó thuộc chatbot.

Bên trong (để hiểu chi phí / lỗi, không cần dùng trực tiếp):

```
kiểm tra đầu vào (+ tự sửa dính furigana) -> SudachiPy tách từ -> tra nghĩa (Mazii + bảng trợ từ)
-> dò mẫu ngữ pháp bằng luật (1612 luật N5–N1) -> 1 lần gọi LLM dựng cấu trúc, dịch, kiểm tra câu
-> code kiểm tra / tự sửa đầu ra LLM (gọi lại model dự phòng nếu sai khuôn) -> ghép kết quả -> cache
```

## 2. Cài đặt

- Python **>= 3.10** (chatbot chạy 3.14 được).
- Cài từ repo riêng (cần quyền đọc repo GitHub `Quan-MM-eUp/bunpo-analyzer-module`):

```bash
pip install "bunpo-analyzer @ git+https://github.com/Quan-MM-eUp/bunpo-analyzer-module.git@<tag hoặc commit>"
# Redis cho nhiều worker:
pip install "bunpo-analyzer[redis] @ git+https://github.com/Quan-MM-eUp/bunpo-analyzer-module.git@<tag hoặc commit>"
```

- Phụ thuộc chính: `pydantic>=2.7`, `pydantic-settings`, `sudachipy` + `sudachidict-core==20261015` (từ điển tách từ khoảng 190 MB sau khi cài, đã ghim phiên bản), `openai>=2.0`, `httpx`, `cryptography`.
- Ghim phiên bản module theo tag / commit: đổi phiên bản có thể đổi khuôn kết quả (xem `schema_version`).

## 3. Cấu hình và dữ liệu cần triển khai

### 3.1. Biến môi trường (tiền tố `BUNPO_`, hoặc file `.env` ở thư mục chạy)

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `BUNPO_DATA_DIR` | **Phải đặt trên server** | `..` (chỉ hợp với máy dev) | Thư mục kho dữ liệu (mục 3.2), nên là **đường dẫn tuyệt đối**. Đường dẫn tương đối (kể cả mặc định của `BUNPO_MAZII_PEM_PATH`) tính từ thư mục làm việc của tiến trình |
| `BUNPO_OPENAI_API_KEY` | **Có** | (rỗng) | Key LLM gateway. Thiếu thì mọi câu trả `llm_unavailable` |
| `BUNPO_OPENAI_BASE_URL` | | `https://llm-api.eup.ai/v1` | LLM gateway (chuẩn OpenAI) |
| `BUNPO_LLM_PROVIDER` | | `openai` | Hiện chỉ hỗ trợ `openai` (mọi gateway chuẩn OpenAI). Giá trị khác: mọi câu trả `llm_unavailable` |
| `BUNPO_LLM_MODEL` | | `gpt-5-mini` | Model phân tích chính |
| `BUNPO_LLM_FALLBACK_MODEL` | | `gpt-4.1` | Gọi lại khi model chính lỗi / sai khuôn |
| `BUNPO_LLM_LIGHT_MODEL` | | `gpt-4.1-mini` | "Dịch nhẹ": câu đã phân tích bằng ngôn ngữ khác |
| `BUNPO_LLM_REASONING_EFFORT` | | `low` | Chỉ cho model suy nghĩ (gpt-5*) |
| `BUNPO_LLM_TIMEOUT_S` | | `30` | Hạn giờ mỗi lần gọi LLM |
| `BUNPO_DICT_PROVIDER` | | `mazii` | `mazii` (nghĩa từ theo ngôn ngữ) hoặc `kho` (word_lib, không gọi mạng) |
| `BUNPO_MAZII_PEM` hoặc `BUNPO_MAZII_PEM_PATH` | Nên có | `../secrets/public.pem` | Nội dung / đường dẫn `public.pem` của app Mazii (giải mã kết quả API). Có cả hai thì dùng `BUNPO_MAZII_PEM`. **Bí mật**: để trong secret manager, không commit, không ghi log. Hậu quả khi thiếu / sai: mục 3.4 |
| `BUNPO_DICT_TIMEOUT_S` | | `1.5` | Hạn giờ mỗi lần gọi Mazii (cả câu tối đa gấp đôi) |
| `BUNPO_DICT_MAX_CONCURRENCY` | | `8` | Số lần gọi Mazii song song mỗi tiến trình |
| `BUNPO_CACHE_BACKEND` | | `memory` | `memory` (1 tiến trình), `redis` (**nên dùng khi nhiều worker**), `none` |
| `BUNPO_CACHE_URL` | Khi redis | | `redis://host:6379/0` |
| `BUNPO_CACHE_TTL_S` | | `2592000` (30 ngày) | Hạn cache kết quả |
| `BUNPO_DEFAULT_LANG` | | `vi` | Ngôn ngữ khi không truyền `lang` |
| `BUNPO_TEXT_FALLBACK_LANG` | | `vi` | Ngôn ngữ dự phòng cho phần chữ lấy từ **kho ngữ pháp** (`grammar[].meaning`, `short_label`, `grammar_detail()`) và **nghĩa trợ từ** (`particle_table`) khi `lang` chưa có bản dịch (mục 9). Một trong 16 mã; mã lạ: lỗi cấu hình. **Chatbot Migii đặt `en`** |
| `BUNPO_MAX_CHARS` | | `100` | Độ dài tối đa một câu |

Có thể truyền cấu hình bằng code thay cho biến môi trường: `Settings(data_dir=..., openai_api_key=...)` rồi đưa vào `analyze_full(..., settings=s)` (mục 4.2).

Mạng ra ngoài server cần mở: LLM gateway (`BUNPO_OPENAI_BASE_URL`) và `https://mazii.net` (POST `/api/search/word/v3`).

### 3.2. Thư mục kho (`BUNPO_DATA_DIR`)

Kho **không** nằm trong package, triển khai riêng (cùng bộ với chatbot):

```
<BUNPO_DATA_DIR>/
├── grammar/grammar_lib.json            kho ngữ pháp gốc (tiếng Việt)            bắt buộc
├── grammar/grammar_text.en.json        bản dịch kho ngữ pháp (hiện có en, ko)  nên có
├── grammar/grammar_text.ko.json
├── word/word_lib.json                  kho từ vựng (dự phòng khi Mazii hỏng)   bắt buộc
└── i18n/<lang>.json                    chép nguyên 15 file i18n của chatbot (module chỉ đọc khoá `label`: tên loại mẫu)  nên có
```

- Thiếu `grammar_text.<lang>.json` thì nội dung mẫu ngữ pháp của ngôn ngữ đó hiện tiếng Việt (không lỗi).
- Dịch thêm ngôn ngữ: chạy `python scripts/translation/publish_lang.py <lang>` trong repo (đã dịch xong kho) rồi chép file mới vào `grammar/`. Kho nạp một lần mỗi tiến trình: **khởi động lại** worker để nhận file mới.
- Bảng trợ từ, luật ngữ pháp, nhãn ngắn, nhãn giao diện nằm sẵn trong package (không cần triển khai riêng).

### 3.3. Kiểm tra khi khởi động

```python
from bunpo_analyzer import check_ready

rep = await check_ready()          # không gọi mạng; check_ready(ping=True) gọi thử Mazii + Redis
if not rep["ok"]:
    log.error("bunpo-analyzer chưa sẵn sàng: %s", rep["checks"])
```

`rep = {"ok": bool, "checks": {"kho", "tokenizer", "llm", "cache", "dictionary": {"ok": bool, "detail": str, "warn"?: true}}}`; riêng `checks.kho` có thêm `langs` (các ngôn ngữ đã có bản dịch kho ngữ pháp, gồm `vi`) và `text_fallback` (giá trị `BUNPO_TEXT_FALLBACK_LANG`; đặt ngôn ngữ dự phòng mà thiếu `grammar_text.<mã>.json` thì `checks.kho` có `warn: true`). `ok = False` khi thiếu thứ bắt buộc (kho, tách từ, key LLM, cache). Mazii hỏng chỉ là `warn` (module tự dùng `word_lib`). Không chứa key. Ví dụ: `docs/examples/check_ready.json`. Nên gọi `check_ready(ping=True)` một lần khi triển khai để phát hiện `public.pem` sai.

### 3.4. Khi Mazii không dùng được

| Tình huống | Module làm gì | Người dùng thấy |
|---|---|---|
| Thiếu `public.pem` (không có biến / không đọc được file) | Ghi log lỗi một lần, cả tiến trình dùng `word_lib` | Tiếng Việt: nghĩa từ `word_lib`. Ngôn ngữ khác: LLM điền nghĩa (`meaning_source = "llm"`) |
| `public.pem` sai, Mazii lỗi mạng / quá giờ | Mỗi từ tra hỏng thì LLM điền nghĩa; 5 lỗi liên tiếp thì ngừng gọi Mazii 60 giây rồi thử lại | Nghĩa từ do LLM điền (vẫn đúng ngôn ngữ, ngắn hơn) |
| `BUNPO_DICT_PROVIDER=kho` | Không gọi Mazii | Như dòng đầu |

`check_ready()` (không ping) đã báo `warn` khi thiếu `public.pem`; `public.pem` sai hoặc Mazii không tới được chỉ phát hiện bằng `check_ready(ping=True)`.

## 4. API công khai

Tất cả import từ `bunpo_analyzer`. Hàm phân tích là **async**.

### 4.1. `analyze()` (dùng hàng ngày)

```python
from bunpo_analyzer import analyze

result = await analyze("雨が降りそうなので、傘を持っていきます。", lang="en")   # -> AnalysisResult (pydantic)
payload = result.model_dump(mode="json", exclude_none=True)                   # JSON gửi app
```

- `analyze(sentence: str, lang: str | None = None, provider: str | None = None) -> AnalysisResult`
- `lang`: một trong 16 mã ở mục 9 (`vi en cn tw ko fr de es pt ru pl id th hi ne my`). Mã khác: **ném `ValueError`** (chatbot nên kiểm tra trước).
- `provider`: tên nhà cung cấp LLM thay cho `BUNPO_LLM_PROVIDER` trong lần gọi này. Hiện chỉ có `openai`: bỏ trống.
- **Không ném lỗi** khi LLM / Mazii / cache hỏng: lỗi nằm trong `result.error` (mục 8). Chỉ ném khi cấu hình / lập trình sai: `ValueError` (lang lạ), `OSError` / `FileNotFoundError` hoặc `json.JSONDecodeError` (kho thiếu / hỏng: lỗi ngay lần gọi đầu, `check_ready` báo trước). Hạn giờ: mỗi lần gọi LLM tối đa `BUNPO_LLM_TIMEOUT_S` (30 s), có thể gọi lại 1–3 lần nên cả lượt có thể quá 60 s trong trường hợp xấu: chatbot nên bọc `asyncio.wait_for(…, 60)` và coi quá giờ như `llm_unavailable`.
- Mỗi lần gọi sinh `result.id` mới (`an_` + 12 ký tự hex), kể cả khi lấy từ cache. Chatbot tự lưu kết quả theo `id` nếu cần mở lại.

### 4.2. `analyze_full()` (khi cần log / cấu hình riêng)

```python
from bunpo_analyzer.core.analyzer import analyze_full

a = await analyze_full(text, lang, settings=None, client=None, kho=None, cache=None, dictionary=None)
a.result        # AnalysisResult (giống analyze)
a.cache         # "miss" (phân tích mới) | "hit" (lấy từ cache) | "light" (cấu trúc từ cache + dịch nhẹ) | "off"
a.latency_ms    # thời gian gọi LLM
a.cost_usd      # chi phí LLM ước tính của lần gọi
a.log_dict()    # dict để ghi log: models, attempt_errors, fixes, misses, dict stats, cost, latency...
```

Tham số phụ (đều tuỳ chọn): `settings` (`bunpo_analyzer.Settings`), `cache` (đối tượng có `async get(key)` / `async set(key, value, ttl_s)` để dùng chung Redis của chatbot), `kho`, `client`, `dictionary`.

### 4.3. `grammar_detail()` (bảng thông tin một mẫu, không gọi AI)

```python
from bunpo_analyzer import grammar_detail

d = grammar_detail(252, "en")      # -> GrammarDetail | None (None: không có mẫu)
d.model_dump(mode="json")
```

Đồng bộ (không async), nhanh (đọc kho trong bộ nhớ). Không kiểm tra `lang`: mã lạ thì nội dung tiếng Việt, `labels[].name` rỗng (endpoint nên kiểm tra `lang` thuộc 16 mã, mặc định `vi`). Mục 6.

### 4.4. `labels()` (chữ hiển thị cho mã trong kết quả)

```python
from bunpo_analyzer import labels, label_langs
L = labels("en")     # dict; ngôn ngữ chưa có -> tiếng Anh. label_langs() -> 16 mã
```

Mục 7.

### 4.5. Khác

- `check_ready(settings=None, ping=False)` (mục 3.3).
- `SCHEMA_VERSION` (`"1.5"`), `__version__` (`"0.2.1"`), `AnalysisResult`, `GrammarDetail` (model pydantic), `Settings`, `get_settings()`.
- Logger: `bunpo_analyzer` (mỗi câu một dòng `analyze {...}` mức INFO), `bunpo_analyzer.llm`, `bunpo_analyzer.dict`, `bunpo_analyzer.cache`. Không bao giờ ghi key / `public.pem`.

## 5. Khuôn kết quả `AnalysisResult` (1.5)

JSON Schema đầy đủ: `docs/schema/analysis_result.schema.json`. Các trường `null` bị bỏ khi dump với `exclude_none=True` (app coi thiếu = null).

### 5.1. Quy ước

1. **Module trả mã, app đổi sang chữ** bằng `labels(lang)` (mục 7): `pos`, `pos_sub`, `role`, `kind`, `input_check.status`, `error.code`.
2. **`span` là khoảng nửa mở `[bắt đầu, kết thúc)` theo số thứ tự token** (`tokens[].i`). Chữ của một dòng = ghép `surface` của các token trong `span`. Riêng `input_check.correction_at` là vị trí **ký tự** trong `correction`.
3. **`nodes` là danh sách phẳng, đã sắp xếp** theo thứ tự hiển thị (duyệt cây theo chiều sâu, anh em xếp theo token đầu tiên); quan hệ cha con qua `parent`. Dòng chủ ngữ ẩn (không `span`) đứng đầu cấp chứa nó (kể cả cấp ngoài cùng). Mỗi cấp có tối đa một dòng chủ ngữ (module bỏ dòng chủ ngữ ẩn nếu cấp đó đã có chủ ngữ thật).
4. Nhóm có `span` tính sẵn để tô nền trên câu gốc. Token thuộc nhiều nhóm thì tô theo nhóm trong cùng (sâu nhất).
5. **Chữ theo `lang`**: `translation`, `nodes[].gloss`, `tokens[].meaning`, `grammar[].meaning`, `grammar[].short_label`, `input_check.reason/explain`. Ngoại lệ (mục 9): `grammar[].meaning`, `short_label` lấy từ kho ngữ pháp, và nghĩa trợ từ (`meaning_source = "particle_table"`): khi `lang` chưa có bản dịch thì dùng ngôn ngữ dự phòng `BUNPO_TEXT_FALLBACK_LANG` (chatbot: tiếng Anh), mặc định tiếng Việt.
6. Trường có dấu `?` ở bảng dưới có thể vắng (null). Token dấu câu (`pos = "punct"`) chỉ có `i`, `surface`, `pos`.

### 5.2. Các trường

| Vị trí | Trường | Kiểu | Ý nghĩa |
|---|---|---|---|
| gốc | `schema_version` | string | `"1.5"` |
| gốc | `id` | string | Mã kết quả (`an_…`), mới mỗi lần gọi |
| gốc | `lang` | string | Ngôn ngữ phần chữ (= tham số) |
| gốc | `text` | string | Câu đã chuẩn hoá (đã tự sửa nếu có `auto_fix`) |
| gốc | `translation` | string? | Bản dịch cả câu. Không có khi lỗi |
| token | `i` | int | Số thứ tự, từ 0 |
| token | `surface` / `base`?, `reading`? | string | Mặt chữ / dạng gốc (từ điển), cách đọc hiragana |
| token | `pos` | mã | `noun`, `verb`, `adj`, `adv`, `prt` (trợ từ), `aux` (trợ động từ, hậu tố), `punct` (dấu câu: không bấm được, không có nghĩa) |
| token | `pos_sub` | mã? | `v1`, `v2`, `v3` (động từ nhóm 1/2/3), `adj_i`, `adj_na` |
| token | `furigana`? | `[[chữ, cách đọc \| null], …]` | Chia đoạn để chỉ gắn furigana lên kanji |
| token | `meaning` | string? | Nghĩa khi bấm vào từ, theo `lang` (Mazii: 1–3 nghĩa khớp từ loại, tối đa khoảng 120 ký tự) |
| token | `meaning_source` | mã? | `dict` (Mazii), `particle_table` (bảng trợ từ của module), `word_lib` (kho, khi không dùng Mazii), `llm` (LLM điền khi tra không ra) |
| token | `level` | string? | Cấp JLPT của từ (chỉ khi `dict`) |
| token | `han` | string? | Âm Hán Việt (chỉ khi `lang = vi` và `dict`) |
| token | `dict_id` | string? | Id mục từ Mazii (để app mở chi tiết từ, nếu muốn) |
| node | `id`, `type`, `parent`? | string, `row` / `group`, string | `parent` vắng: ngoài cùng |
| node | `gloss` | string? | Nghĩa của phần đó trong câu (theo `lang`). Nhóm cũng có: nghĩa cả mệnh đề (hiện cạnh tiêu đề nhóm) |
| node | `main`, `hidden` | bool | Luôn có, `false` với nhóm |
| node | `grammar` | int[] | Id mẫu ngữ pháp gắn vào dòng / nhóm (tra trong `grammar[]` của kết quả) |
| row | `role` | mã | `subject`, `topic`, `object`, `complement`, `predicate`, `adv_time`, `adv_place`, `adv_manner`, `adv_reason` |
| row | `span` | `[int, int]`? | Không có ở dòng chủ ngữ ẩn |
| row | `jp` | string? | Chữ của dòng ẩn, ví dụ `（私が）` |
| row | `main` | bool | Vị ngữ chính (nhãn: `labels()["role"]["main_predicate"]`) |
| row | `hidden` | bool | Chủ ngữ ẩn (nhãn: `labels()["role_hidden"].format(role=...)`, viền nét đứt) |
| group | `kind` | mã | `rel` (mệnh đề bổ nghĩa danh từ), `sub` (vế phụ), `quote` (trích dẫn), `nominal` (mệnh đề danh từ hoá) |
| group | `span` | `[int, int]` | Phạm vi nhóm, để tô nền |
| group | `head`, `head_text` | int?, string? | Danh từ được bổ nghĩa (chỉ `rel`). Tiêu đề: `labels()["kind_rel_for"].format(head=head_text)` |
| grammar | `id` | int | Id trong `grammar_lib` (mở bảng: `grammar_detail(id, lang)`) |
| grammar | `short_label` | string? | Nhãn ngắn trên thẻ, ví dụ `～そう［có vẻ］` / `～たことがある` |
| grammar | `level` | string? | `N5`…`N1` |
| grammar | `meaning` | string? | Nghĩa chuẩn của mẫu (từ kho, theo `lang`) |
| grammar | `note` | string? | Hiện luôn `null` (để dành) |
| gốc | `input_check` | object | `status`: `ok` / `suspect` / `error`. `suspect`: `at` (span token), `reason`. `error`: `at`, `explain`, `correction` (câu đúng), `correction_at` (span **ký tự** phần đã sửa trong `correction`) |
| gốc | `auto_fix` | object? | `{original, fixed}`: module đã tự bỏ furigana dính trong câu (見みた → 見た) |
| gốc | `error` | object? | `{code, reason?}`. `code`: `invalid_input`, `grammar_error`, `structure_failed`, `llm_unavailable` (mục 8). `reason` chỉ có ở `invalid_input` (`not_japanese`, `multiple_sentences`, `too_long`) và `llm_unavailable` / `structure_failed` do gateway hết ngân sách (`quota`); còn lại vắng |

Có gì theo từng trường hợp:

| Trường hợp | `tokens` | `translation`, `nodes`, `grammar` | `input_check` | `error` |
|---|---|---|---|---|
| Câu đúng | có | có | `ok` | null |
| Nghi sai | có | có | `suspect` + `at`, `reason` | null |
| Sai ngữ pháp | có | **không** | `error` + `at`, `explain`, `correction`, `correction_at` | `grammar_error` |
| Đầu vào lỗi | **không** | không | `ok` | `invalid_input` + `reason` |
| LLM lỗi | có (nghĩa từ vẫn có, trừ từ cần LLM) | không | `ok` | `structure_failed` / `llm_unavailable` |

### 5.3. Ví dụ (rút gọn, `lang = "en"`)

Rút gọn cho dễ đọc: bỏ `main` / `hidden` khi `false` và `grammar` khi rỗng (kết quả thật luôn có, xem `docs/examples/`). Schema đánh dấu `tokens`, `nodes`, `grammar` là tuỳ chọn vì có giá trị mặc định `[]`; thực tế luôn có mặt.

```json
{
  "schema_version": "1.5",
  "id": "an_3f9c2a71b0de",
  "lang": "en",
  "text": "昨日友達と見た映画はとても面白かったです。",
  "translation": "The movie I watched with a friend yesterday was very interesting.",
  "tokens": [
    {"i": 0, "surface": "昨日", "base": "昨日", "reading": "きのう", "pos": "noun", "furigana": [["昨日", "きのう"]],
     "meaning": "yesterday", "meaning_source": "dict", "level": "N5", "dict_id": "…"},
    {"i": 1, "surface": "友達", "base": "友達", "reading": "ともだち", "pos": "noun", "furigana": [["友達", "ともだち"]],
     "meaning": "friend; companion", "meaning_source": "dict", "level": "N5", "dict_id": "…"},
    {"i": 2, "surface": "と", "base": "と", "reading": "と", "pos": "prt", "furigana": [["と", null]],
     "meaning": "and, with; that (quotation)", "meaning_source": "particle_table"},
    {"i": 3, "surface": "見", "base": "見る", "reading": "み", "pos": "verb", "pos_sub": "v2", "furigana": [["見", "み"]],
     "meaning": "to see; to look; to watch; to view; to observe; to examine; …", "meaning_source": "dict", "level": "N5", "dict_id": "…"},
    {"i": 4, "surface": "た", "base": "た", "reading": "た", "pos": "aux", "furigana": [["た", null]],
     "meaning": "past, did (completion)", "meaning_source": "particle_table"},
    "… token 5–10 …",
    {"i": 11, "surface": "。", "pos": "punct"}
  ],
  "nodes": [
    {"id": "g1", "type": "group", "kind": "rel", "span": [0, 5], "head": 5, "head_text": "映画", "grammar": [196]},
    {"id": "r1", "type": "row", "parent": "g1", "role": "subject", "hidden": true, "jp": "（私が）", "gloss": "I"},
    {"id": "r2", "type": "row", "parent": "g1", "role": "adv_time", "span": [0, 1], "gloss": "yesterday"},
    {"id": "r3", "type": "row", "parent": "g1", "role": "complement", "span": [1, 3], "gloss": "with a friend", "grammar": [19]},
    {"id": "r4", "type": "row", "parent": "g1", "role": "predicate", "span": [3, 5], "gloss": "watched"},
    {"id": "r5", "type": "row", "role": "topic", "span": [5, 7], "gloss": "the movie"},
    {"id": "r6", "type": "row", "role": "predicate", "span": [7, 11], "gloss": "was very interesting", "main": true, "grammar": [43, 26]}
  ],
  "grammar": [
    {"id": 196, "short_label": "V plain form + N", "level": "N5", "meaning": "…"},
    {"id": 19, "short_label": "N と", "level": "N5", "meaning": "With …"}
  ],
  "input_check": {"status": "ok"}
}
```

Ví dụ thật đầy đủ (chạy bằng `scripts/build_doc_examples.py`): `docs/examples/analyze_ok_vi.json`, `analyze_ok_en_light.json` (cùng câu, ngôn ngữ khác, dịch nhẹ từ cache), `analyze_ok_ko.json`, `analyze_grammar_error_en.json`, `analyze_auto_fix_vi.json`, `analyze_invalid_not_japanese.json`, `analyze_invalid_multiple.json`.

### 5.4. App dựng màn hình từ khuôn này

| Phần trên app | Lấy từ |
|---|---|
| Câu gốc, furigana, gạch chân màu theo từ loại | `tokens[].furigana`, `tokens[].pos` |
| Nền màu nhóm mệnh đề trên câu gốc | `nodes` loại `group`: `kind`, `span` |
| Dòng chi tiết khi bấm một từ: `見【み】 · Group 2 verb · dictionary form 見る · to see… · N5`; tiếng Việt: `見【み】 · KIẾN · động từ nhóm 2 · dạng gốc 見る · nhìn, xem · N5` | Theo thứ tự, nối bằng ` · `, phần vắng thì bỏ: `surface` + `【reading】` (khi `reading ≠ surface`); `han` (chỉ tiếng Việt); `labels.pos_sub[pos_sub]` hoặc `labels.pos[pos]`; `labels.base_form` + `base` (khi `base ≠ surface` và `pos` là `verb` / `adj`); `meaning` (nguyên văn, cho xuống dòng nếu dài); `level`. Token `punct` không bấm được |
| Bản dịch | `translation` |
| Cấu trúc câu (Dòng / Nhóm) | `nodes`: nhãn từ `labels()`, chữ = ghép token trong `span` (hoặc `jp`), `gloss`, nhãn mẫu `grammar[id].short_label · level` |
| Danh sách "Ngữ pháp trong câu" | `grammar[]`: `short_label · level — meaning`, bấm mở `grammar_detail(id, lang)` |
| Thẻ kết quả trong khung chat | `text`; dòng phụ: cấp cao nhất trong `grammar[].level` (N1 cao nhất; không có mẫu thì `null`) + số mẫu `len(grammar)`; nút mở màn hình theo `id` |
| Tiêu đề nhóm | `labels.kind[kind]`; nhóm `rel` có `head_text`: `labels.kind_rel_for.format(head=head_text)`; kèm `gloss` của nhóm và nhãn mẫu |
| Màn hình khi `structure_failed` / `llm_unavailable` | Chỉ thẻ 1 (câu gốc, bấm từ xem nghĩa); không có thẻ dịch, cấu trúc, ngữ pháp |

## 6. Bảng ngữ pháp `GrammarDetail`

`grammar_detail(id, lang)` trả nội dung một mẫu, lấy thẳng từ kho (không gọi AI), dùng cho bảng thông tin trượt lên khi bấm một mẫu. Schema: `docs/schema/grammar_detail.schema.json`, ví dụ: `docs/examples/grammar_detail_252_en.json`.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id`, `lang` | int, string | Như tham số |
| `text_lang` | string | Ngôn ngữ thực của phần chữ: `lang` nếu đã có bản dịch; chưa có thì ngôn ngữ dự phòng (`BUNPO_TEXT_FALLBACK_LANG`, nếu kho có bản dịch của nó); không thì `vi` |
| `short_label`, `name` | string? | Nhãn ngắn; tên đầy đủ trong kho |
| `reading` | string? | Cách đọc kana (hiện khi nhãn có kanji) |
| `level` | string? | `N5`…`N1` |
| `labels` | `[{code, name?}]` | Loại mẫu (`grammar_basic`…); `name` theo `lang` từ `i18n/<lang>.json` của kho (tiếng Việt chưa có tên) |
| `connection` | string? | Cách nối (`接続`), ví dụ `Vた + ことがある` |
| `meaning` | string? | Ý nghĩa |
| `examples` | `[{jp, vi?, tr?, dialog}]` | Tối đa 6 câu, câu đơn trước hội thoại. **`tr` là bản dịch theo `lang`** (chưa dịch thì bằng `vi`): app hiển thị `tr`. `dialog = true`: hội thoại A/B, `jp`/`tr` có nhiều dòng (`\n`) |
| `explain` | string? | Giải thích chi tiết (nên thu gọn sau nút "Xem giải thích chi tiết") |
| `comparison` | `{headers, rows}`? | Bảng so sánh; ô có thể chứa `<ruby>漢字<rt>かんじ</rt></ruby>` (thẻ HTML duy nhất) |
| `mistakes` | string[] | Lỗi hay gặp, mỗi lỗi một dòng (dùng × / ○ đánh dấu sai / đúng) |
| `notes` | string? | Ghi chú |
| `confusable` | `[{id, short_label, level}]` | "Dễ nhầm với": bấm mở `grammar_detail(id, lang)` khác |

- Không có mẫu: trả `None` (endpoint nên trả 404).
- Id của mẫu trùng đã gộp vẫn mở được. Với ngôn ngữ khác tiếng Việt, nếu mẫu trùng chưa có bản dịch riêng thì trả nội dung đã dịch của mẫu chuẩn (giữ `id` đã hỏi).

## 7. Nhãn giao diện `labels(lang)`

Chữ hiển thị cho mọi mã trong kết quả, 16 ngôn ngữ (thuật ngữ thống nhất với bản dịch kho ngữ pháp). Ngôn ngữ / mục chưa có: tiếng Anh. Trả bản sao (sửa thoải mái). Ví dụ đầy đủ: `docs/examples/labels_vi.json`, `labels_en.json`, `labels_ko.json` (ví dụ tiếng Hàn: `role_hidden` = `{role} (생략)`, `kind_rel_for` = `「{head}」 수식절`, `main_predicate` = `주 술어`).

```python
L = labels("en")
L["pos"]["verb"]               # "verb"                      tokens[].pos
L["pos_sub"]["v1"]             # "Group 1 verb"              tokens[].pos_sub (ưu tiên hơn pos)
L["base_form"]                 # "dictionary form"           chữ trước tokens[].base
L["role"]["subject"]           # "Subject"                   nodes[].role
L["role"]["main_predicate"]    # "Main predicate"            nodes[].main = true
L["role_hidden"]               # "{role} (omitted)"          nodes[].hidden: .format(role=L["role"][role])
L["kind"]["sub"]               # "Subordinate clause"        nodes[].kind
L["kind_rel_for"]              # "Clause modifying {head}"   kind = rel có head_text: .format(head=head_text)
L["check"]["suspect"]          # "May be unnatural"          input_check.status (suspect / error)
L["error"]["grammar_error"]    # "Grammar error"             error.code
```

Các nhãn này là tên ngắn. Câu thông báo trong chat (lời nhắc gửi lại câu, xin lỗi khi AI lỗi…) do chatbot tự viết theo giọng Sensei, đặt trong `i18n` của chatbot (gợi ý tiếng Việt ở mục 8).

## 8. Xử lý từng trường hợp

Các tin nhắn **cộng dồn** theo thứ tự: (1) `error.code = invalid_input` thì chỉ nhắc rồi dừng; (2) có `auto_fix` thì báo đã sửa (kể cả khi sau đó là câu sai); (3) xử lý theo `error.code` / `input_check.status` như bảng. Nhãn trạng thái `ok` không có chữ (không hiện gì).

| Trường hợp | Nhận biết | Chatbot nên làm | Gợi ý tin nhắn (vi) |
|---|---|---|---|
| Đầu vào lỗi | `error.code = "invalid_input"`, `reason`: `not_japanese` / `multiple_sentences` / `too_long` | Không hiện thẻ; nhắc người dùng. Nên chặn trước khi gọi module (mục 11.3) | "Mình chỉ phân tích câu tiếng Nhật thôi…" / "Bạn gửi từng câu một nhé…" / "Câu dài quá (tối đa 100 ký tự)…" |
| Tự sửa dính furigana | `auto_fix` khác null | Báo đã sửa, rồi xử lý tiếp như thường (kết quả là của câu đã sửa `text`) | "Mình đã sửa câu của bạn thành: {auto_fix.fixed}" |
| Sai ngữ pháp | `error.code = "grammar_error"` | Thẻ lỗi ngay trong chat: câu gốc tô đỏ phần `at`, `explain`, câu đúng `correction` tô xanh phần `correction_at`. Không mở màn hình phân tích | Tiêu đề: `labels.check.error` |
| Nghi sai | `input_check.status = "suspect"` | Cảnh báo nhẹ (`reason`, chỗ `at`) + thẻ kết quả như câu đúng | "Câu này có thể chưa chuẩn ở 「…」. {reason}" |
| Câu đúng | `error` null, `status = "ok"` | Tin nhắn ngắn + thẻ kết quả (nút "Xem phân tích") | "Mình phân tích xong câu của bạn rồi!" |
| Không dựng được cấu trúc | `error.code = "structure_failed"` (LLM trả sai khuôn cả khi gọi lại) | Vẫn có `tokens`: hiện thẻ kết quả (dòng phụ: chỉ có cách đọc và nghĩa từ), màn hình chỉ có thẻ câu gốc; không trừ lượt | "Mình chưa phân tích được cấu trúc câu này, bạn xem tạm cách đọc và nghĩa từ nhé." |
| AI lỗi / hết ngân sách | `error.code = "llm_unavailable"` (`reason = "quota"` ở cả `llm_unavailable` lẫn `structure_failed`: gateway hết ngân sách) | Như trên; không trừ lượt; không cache (gọi lại sau sẽ thử lại) | "Không gọi được AI lúc này. Tạm thời bạn xem cách đọc và nghĩa từ nhé." |
| Quá giờ phía chatbot (`asyncio.wait_for` hết hạn) | Không có kết quả | Chỉ tin nhắn, không thẻ (`navigation = null`), không lưu, không trừ lượt | "Không gọi được AI lúc này, bạn thử lại sau nhé." |

**Đổi `at` (span token) sang vị trí ký tự** (app ở màn chat không có danh sách token):

```python
def char_span(result: dict, at):
    """[token đầu, token cuối) -> [ký tự đầu, ký tự cuối) trong result["text"]."""
    if not at:
        return None
    pos, out = 0, {}
    for t in result["tokens"]:
        out[t["i"]] = (pos, pos + len(t["surface"]))
        pos += len(t["surface"])
    return [out[at[0]][0], out[at[1] - 1][1]]
```

(`text` bằng đúng phép ghép `surface` của các token. `at` dùng `result["text"]`, không dùng tin nhắn gốc của người dùng.)

**Bản chữ của thẻ báo lỗi** (gửi qua `token`, sau tin "đã sửa câu" nếu có). App chưa hỗ trợ thẻ đọc chữ này; app hỗ trợ thì ẩn phần chữ từ dòng `⚠` trở đi và dựng thẻ từ `done.grammar_error` (tin "đã sửa câu" phía trước vẫn hiện). Nhãn `Câu của bạn` / `Lỗi` / `Câu đúng` là khoá `bunpo_error_you` / `bunpo_error_why` / `bunpo_error_fix` dịch theo ngôn ngữ người dùng:

```
⚠ {labels.check.error}
✕ Câu của bạn: {text, phần at bọc trong 【】}
Lỗi: {explain}
✓ Câu đúng: {correction, phần correction_at bọc trong 【】}
```

Ví dụ: `✕ Câu của bạn: 映画は【面白いでした】。` / `✓ Câu đúng: 映画は面白【かったです】。`

**Khoá i18n gợi ý cho tin nhắn của chatbot** (chatbot tự dịch 15 ngôn ngữ, cùng chỗ với các khoá hiện có): `bunpo_done` (phân tích xong), `bunpo_auto_fix` (`{fixed}`), `bunpo_suspect` (`{part}`, `{reason}`), `bunpo_err_not_japanese`, `bunpo_err_multiple`, `bunpo_err_too_long` (`{max}`), `bunpo_err_structure`, `bunpo_err_ai`, `bunpo_error_you`, `bunpo_error_why`, `bunpo_error_fix` (3 nhãn của thẻ lỗi).

## 9. Ngôn ngữ

16 mã `lang`: `vi` (gốc) và `en`, `cn` (Trung giản thể), `tw` (Trung phồn thể), `ko`, `fr`, `de`, `es`, `pt`, `ru`, `pl`, `id`, `th`, `hi`, `ne`, `my` (trùng mã file `i18n` của chatbot).

Phần do LLM viết (`translation`, `gloss`, `input_check.reason/explain`) luôn theo `lang`. Các phần còn lại phụ thuộc dữ liệu đã dịch. Chỗ chưa có bản dịch dùng **ngôn ngữ dự phòng** `BUNPO_TEXT_FALLBACK_LANG` (từ 0.2.1; mặc định `vi`, chatbot Migii đặt `en`):

| Phần | vi | en, ko | id, tw, cn | fr, de, es, pt, ru, pl, th, hi, ne, my |
|---|---|---|---|---|
| Nghĩa từ (Mazii) | có | có | có | có (`pl` dùng từ điển tiếng Anh) |
| Nghĩa trợ từ / trợ động từ (`particle_table`) | có | có | có | **ngôn ngữ dự phòng** (bản dịch đã có sẵn, bật bằng `export_particles.py --langs …`) |
| Kho ngữ pháp: `grammar[].meaning`, `short_label`, `grammar_detail()` | có | có | **ngôn ngữ dự phòng** (chờ dịch kho) | **ngôn ngữ dự phòng** (chờ dịch kho) |
| `labels()` | có | có | có | có |

Thứ tự chọn chữ: bản dịch của `lang` → bản dịch của ngôn ngữ dự phòng → tiếng Việt (bản gốc). Người dùng tiếng Việt luôn thấy bản gốc. Ngôn ngữ đã có file dịch nhưng thiếu một mẫu hoặc một trường thì giữ như cũ (trường thiếu dùng tiếng Việt). Ngôn ngữ dự phòng không ảnh hưởng phần LLM viết và nghĩa từ Mazii, cũng không nằm trong khoá cache (cache chỉ giữ đầu ra LLM; phần chữ kho và nghĩa trợ từ ghép lại mỗi lần gọi), nên đổi biến này không cần xoá cache. `analyze_full(settings=…)` dùng giá trị trong `settings` của lần gọi; `grammar_detail()` gọi thẳng dùng biến môi trường (`get_settings()`). Biết phần kho đã dịch chưa: `grammar_detail().text_lang`, hoặc `lang in check_ready()["checks"]["kho"]["langs"]` (áp dụng cho `grammar[]` của `AnalysisResult`, vốn không có trường `text_lang`). `grammar_detail().labels[].name` lấy từ `i18n` nên luôn theo `lang`. Khi một ngôn ngữ dịch kho xong: `publish_lang.py <lang>` → chép `grammar_text.<lang>.json` vào `grammar/` → khởi động lại. Không cần đổi code chatbot.

## 10. Hiệu năng, chi phí, chạy đồng thời

Số đo trên gateway nội bộ (gpt-5-mini, suy nghĩ thấp), lần chạy `scripts/build_doc_examples.py` ngày 09/11/2026 (số từng câu trong `meta` của `docs/examples/analyze_*.json`; `latency_ms` là phần LLM, `wall_ms` là cả lượt gọi):

| Tình huống | Thời gian cả lượt | Chi phí LLM |
|---|---|---|
| Câu mới (`cache = "miss"`) | 5–15 giây (đo được: câu sai 5,0 s; 6,9 s; 9,4 s; 15,0 s), trong đó LLM 4–13 s | $0,0013–0,0035; khi phải gọi lại model dự phòng (gpt-4.1) tới khoảng $0,0125 |
| Câu đã phân tích, cùng ngôn ngữ (`hit`) | khoảng 10 ms | 0 |
| Câu đã phân tích bằng ngôn ngữ khác (`light`) | khoảng 3,5 giây (LLM 2,2 s, còn lại tra Mazii theo ngôn ngữ mới) | khoảng $0,0005 |
| Tra Mazii (song song, trước khi gọi LLM) | mỗi từ trung vị khoảng 0,35 s; cả câu tối đa 3 s; từ đã tra lấy từ cache 30 ngày | 0 |
| Đầu vào lỗi | vài ms, không gọi mạng | 0 |

- App cần trạng thái "đang phân tích" khoảng 10 giây (nên có hiệu ứng chờ, không chặn khung chat).
- Khởi động tiến trình: nạp kho khoảng 1 giây (lần gọi đầu, hoặc gọi `check_ready()` lúc khởi động để nạp trước). Bộ nhớ khoảng 270 MB mỗi tiến trình (từ điển tách từ + kho).
- **Cache:** khoá gồm câu, phiên bản khuôn, prompt, kho, luật, bảng trợ từ, từ điển tách từ, model và nguồn nghĩa từ, nên đổi bất kỳ thứ gì thì mục cũ tự hết hiệu lực, không cần xoá tay. Nhiều worker: dùng `redis` để chia sẻ cache (kể cả cache tra từ Mazii). Cache hỏng thì bỏ qua, vẫn phân tích.
- **Chạy đồng thời:** hàm async, an toàn khi nhiều yêu cầu cùng lúc trong **một event loop** (FastAPI / uvicorn: mỗi worker một loop, đúng cách dùng). Kho, luật, từ điển Mazii (kèm `httpx.AsyncClient`) là đối tượng dùng chung trong tiến trình. **Không** gọi `asyncio.run(analyze(...))` nhiều lần trong cùng tiến trình khi dùng Mazii (client HTTP gắn với loop đầu tiên): script chạy lô nên gom vào một `asyncio.run`.
- Mazii lỗi 5 lần liên tiếp thì ngừng gọi 60 giây (từ cần nghĩa chuyển sang LLM điền), tự gọi lại sau đó.
- **Chạy lô** (ví dụ 1.000 câu mỗi đêm): gọi `check_ready()` trước, gom vào **một** `asyncio.run`, giới hạn song song bằng `asyncio.Semaphore(4)` (tăng dần nếu gateway chịu được; module không tự giới hạn số lần gọi LLM), dùng `analyze_full` để cộng `cost_usd`. Chi phí ước khoảng $1,3–3,5 cho 1.000 câu mới. Câu trùng nhau lấy từ cache.

## 11. Tích hợp vào chatbot hiện tại (từng bước)

Chatbot hiện tại: FastAPI; mỗi tin nhắn qua bước phân loại intent; `POST /ai/sensei/message` trả SSE gồm `meta` (đầu tiên), nhiều `token` (`{"t": "..."}`: chữ bong bóng chat), `done` (dữ liệu có cấu trúc: `intent`, `source`, `navigation` tối đa 1 nút `{type, params, label}`, `choices`, `quota_remaining`…), `error`, `timeout` (app chuyển sang polling). App gặp `navigation.type` lạ thì bỏ qua; chỉ thêm trường, không đổi trường cũ. Tính năng chỉ bật ở API **v3** (`SENTENCE_ANALYSIS_ENABLED=true`), v1 và v2 tắt (yêu cầu phân tích câu ở đó xử lý như hiện nay).

1. **Cài và cấu hình:** thêm package (mục 2), biến môi trường (mục 3.1), triển khai thư mục kho (mục 3.2), `public.pem` vào secret. Lúc khởi động gọi `check_ready()` và ghi log (mục 3.3).
2. **Intent mới `sentence_analysis`** trong bước phân loại; `targets` chứa câu tiếng Nhật đã tách khỏi tin nhắn.
3. **Chặn đầu vào trước khi gọi module** (module vẫn kiểm tra lại): nhiều câu (bỏ phần trong 「」『』, đếm 。！？ còn chữ theo sau), quá 100 ký tự, không có chữ Nhật, chỉ một từ (chuyển sang tra từ). Lượt bị chặn: không gọi module.
4. **Gọi** `result = await analyze(text, lang=<ngôn ngữ tài khoản>)`. `lang` lấy từ cài đặt tài khoản, không để LLM đoán. Bọc thêm hạn giờ phía chatbot nếu cần (ví dụ 60 s).
5. **Lưu** `result.model_dump(mode="json", exclude_none=True)` theo `result.id`, gắn với người dùng và phiên (để mở màn hình, mở lại từ lịch sử, trả lời câu hỏi nối tiếp).
6. **Trả SSE theo trường hợp** (mục 8): tin nhắn ngắn qua `token` (chữ cố định trong `i18n`, `source: "template"`), và trong `done`:
   - Có `tokens` (câu đúng, nghi sai, `structure_failed`, `llm_unavailable`): `navigation = {"type": "grammar_analysis", "params": {"analysis_id": id, "level": <cấp cao nhất hoặc null>, "grammar_count": len(grammar)}, "label": text}`, `grammar_error = null`, `intent = "sentence_analysis"`, `source = "template"`.
   - Sai ngữ pháp: `grammar_error = {"text", "at": char_span(result, input_check.at), "explain", "correction", "correction_at"}` + bản chữ của thẻ lỗi qua `token` (mục 8); `navigation = null`; `source = "llm"`. Nghi sai không có trường riêng trong `done`: chỉ là tin nhắn `token`.
   - Đầu vào lỗi: chỉ tin nhắn nhắc, `navigation = null`, `grammar_error = null`, không lưu kết quả.
   - Mọi trường hợp: `intent = "sentence_analysis"`; `source = "llm"` khi có `grammar_error`, còn lại `"template"`.
   - Mọi bản API đều có khoá `grammar_error` trong `done` (v1, v2 luôn `null`).
7. **Endpoint mới** (cùng xác thực, kiểm tra kết quả thuộc người gọi):
   - `GET /ai/sensei/analysis/{analysis_id}` → kết quả đã lưu, nên kèm `"labels": labels(result.lang)` để app không cần tự dịch mã.
   - `GET /ai/sensei/grammar/{id}?lang=…` → `grammar_detail(id, lang)` (404 nếu `None`; `lang` không thuộc 16 mã thì dùng ngôn ngữ tài khoản).
   - Kết quả nên giữ ít nhất bằng thời gian giữ lịch sử chat (để mở lại từ lịch sử); con số cụ thể chờ leader chốt.
8. **Câu hỏi nối tiếp** ("sao dùng が?"): đọc lại kết quả đã lưu, đưa LLM của chatbot bản tóm tắt ngắn, **không** để LLM viết lại thẻ phân tích:

```python
def summary_for_llm(r: dict) -> str:
    g = "; ".join(f"{x['short_label']} ({x['level']}): {x.get('meaning') or ''}"[:160] for x in r.get("grammar", []))
    return f"Câu: {r['text']}\nDịch: {r.get('translation') or ''}\nMẫu ngữ pháp: {g or 'không có'}"
```

9. **Quota** (đề xuất, chờ leader chốt): phân tích thành công, nghi sai, báo câu sai: trừ lượt. Bị chặn trước khi gọi module hoặc module trả `invalid_input`: trừ (giữ quy tắc hiện tại "mọi lượt đều trừ"; chỗ chặn quota nằm trước bước phân loại intent trong `engine.handle`). Lỗi AI (`structure_failed`, `llm_unavailable`, quá giờ phía chatbot): không trừ. Mở màn hình / bảng ngữ pháp: không trừ.
10. **Log:** nếu dùng `analyze_full`, ghi `a.log_dict()` (model, chi phí, độ trễ, cache, chỗ code tự sửa) cùng id tin nhắn.

## 12. Hạn chế đã biết

- Kho ngữ pháp mới dịch en, ko; ngôn ngữ khác hiện tiếng Việt ở phần lấy từ kho (mục 9). Mẫu #1015 có nghĩa tiếng Việt viết không dấu nên chưa được dịch.
- Nghĩa từ tiếng Việt từ Mazii đôi khi xếp nghĩa phụ lên trước (登る, 今日, 明日); từ đồng âm khác nghĩa (つく) chưa chọn theo ngữ cảnh. Đánh giá: `docs/mazii_eval.md` (khoảng 90% từ nội dung có nghĩa từ Mazii, khoảng 95% chấp nhận được khi duyệt tay).
- Kiểm tra câu sai do LLM: có thể báo nhầm `suspect` với văn nói, lời bài hát; `error` chỉ dùng cho lỗi rõ ràng.
- Bộ luật dò mẫu và một số nội dung kho đang chờ duyệt (`docs/rules_N*.md`, `docs/kho_loi_du_lieu.md`): sửa kho / luật là đổi khoá cache, kết quả cũ tự hết hiệu lực.
- Kho còn lỗi dữ liệu hiện nguyên văn (module không sửa kho), ví dụ trong `docs/examples/`: `grammar[].meaning` của mẫu #26 có chữ 【ảnh】 / 【사진】 (chỗ ảnh trong kho), `notes` của mẫu #338 chứa nguyên khối "meaning_vi: … ⏐ examples:", `reading` của #338 chứa kanji. Câu ví dụ hội thoại viết liền trên một dòng (「…」「…」) không được nhận là hội thoại (`dialog = false`).
- Quyền dùng API Mazii và giới hạn gọi: giả định đã được phép; cần xác nhận với team Mazii trước khi chạy thật ở quy mô lớn.
- Chỉ hỗ trợ nhà cung cấp LLM chuẩn OpenAI (`llm_provider = openai`).

## 13. Câu hỏi thường gặp

**Muốn tắt Mazii (không gọi mạng ngoài)?** `BUNPO_DICT_PROVIDER=kho`: nghĩa từ lấy từ `word_lib` (chỉ tiếng Việt, ngôn ngữ khác do LLM điền).

**Cùng câu, hai người dùng khác ngôn ngữ?** Người thứ hai được "dịch nhẹ" từ cấu trúc đã cache (`light`), không phân tích lại.

**Kết quả có thay đổi khi gọi lại cùng câu?** Trong hạn cache thì giống hệt (trừ `id`). Hết cache hoặc đổi phiên bản kho / prompt thì LLM chạy lại, có thể khác chút ở `gloss`, `translation`.

**App bản cũ gặp trường mới?** Khuôn chỉ thêm trường, không đổi trường cũ; `schema_version` để app nhận biết.

**Kiểm thử phía chatbot không gọi LLM?** Thay `analyze` bằng hàm giả trả `AnalysisResult.model_validate(json.load(open("docs/examples/analyze_ok_vi.json"))["result"])` (mỗi file ví dụ có `call`, `meta`, `result`); `grammar_detail`, `labels` không gọi mạng nên dùng thật được.

**Thêm ngôn ngữ dịch kho?** Mục 3.2, 9. Không đổi code.

**Chuỗi rỗng, một từ?** Chuỗi rỗng / chỉ khoảng trắng: `invalid_input` + `not_japanese`. Một từ (猫) vẫn được phân tích như một câu, nên chatbot chặn trước và chuyển sang tra từ (mục 11, bước 3).

**Bảng trợ từ có những ngôn ngữ nào?** Cố định theo phiên bản package (0.2.0: en, id, tw, cn, ko; xem `CHANGELOG.md` khi nâng phiên bản).

**Một mẫu lẻ vẫn tiếng Việt dù `lang` đã có trong `kho.langs`?** Có thể (ví dụ #1015, nội dung kho viết không dấu nên chưa dịch). Coi như hạn chế dữ liệu, không cần xử lý riêng.
