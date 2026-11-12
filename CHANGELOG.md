# Thay đổi

## 0.2.3 (khuôn kết quả 1.5, không đổi)

- `tables/particle_table.fr.json`: nghĩa trợ từ / trợ động từ tiếng Pháp (bản dịch C2). Đổi bảng là đổi khoá cache.
- Kho: thêm bản dịch kho ngữ pháp tiếng Pháp (`grammar/grammar_text.fr.json`, 1491/1491 mẫu, repo dịch) — chép vào thư mục kho khi triển khai.

## 0.2.2 (khuôn kết quả 1.5, không đổi)

**Nghĩa trợ từ thêm 3 ngôn ngữ**
- `tables/particle_table.th.json`, `.ru.json`, `.es.json` (bản dịch C2): người dùng tiếng Thái, Nga, Tây Ban Nha thấy nghĩa trợ từ / trợ động từ đúng ngôn ngữ (trước dùng ngôn ngữ dự phòng hoặc tiếng Việt). Đổi bảng là đổi khoá cache.

**Dữ liệu kho (triển khai lại thư mục kho)**
- Sửa `grammar_lib.json`: #26, #27 (bỏ chỗ ảnh 【ảnh】 trong `meaning_vi`) và 13 lỗi trong `LOI_NGUON_BTV.md` của repo dịch (#632 #510 #1335 `notes`, #1290 `explain`, #1085, chữ Nhật gõ sai ở #594 #964 #966 #981 #984 #1086 #1087, #1015). Bản dịch kho (`grammar_text.<lang>.json`: en, ko, id, cn, th, ru, es) đã cập nhật theo; chép cùng `grammar_lib.json`.

**Công cụ dịch kho**
- `publish_lang.py`: dịch bù khi kho sửa sau khi dịch (`translation/patches/<lang>.json`, danh sách cần dịch ở `patches/<lang>.todo.json`); các trường không đổi giữ bản dịch cũ.
- `check.py`: bớt báo nhầm "chưa dịch (còn nhiều kana)" (tiếng Trung giữ mẫu trong 「」, cụm ngắn, dòng ×/○ chép từ nguồn); câu Nhật dài chép nguyên từ nguồn vẫn bị báo.

## 0.2.1 (khuôn kết quả 1.5, không đổi)

**Ngôn ngữ dự phòng cho phần chữ lấy từ kho**
- Biến mới `BUNPO_TEXT_FALLBACK_LANG` (mặc định `vi`: giữ hành vi cũ). Khi `lang` chưa có bản dịch: kho ngữ pháp (`grammar[].meaning`, `short_label`, `grammar_detail()` gồm câu ví dụ `tr`) và nghĩa trợ từ (`particle_table`) dùng bản dịch của ngôn ngữ dự phòng, rồi mới tới tiếng Việt. Người dùng tiếng Việt không đổi.
- `grammar_detail().text_lang` báo ngôn ngữ thật của chữ (vd. `en` khi `lang = fr` và dự phòng `en`); `labels[].name` vẫn theo `lang`.
- `check_ready()`: `checks.kho.text_fallback`; cảnh báo (`warn`) khi đặt ngôn ngữ dự phòng mà kho thiếu `grammar_text.<mã>.json`.
- Không đổi khoá cache (cache chỉ giữ đầu ra LLM).

## 0.2.0 (khuôn kết quả 1.5)

**Tra nghĩa từ bằng Mazii**
- Mặc định `BUNPO_DICT_PROVIDER=mazii`: nghĩa từ nội dung lấy từ API Mazii theo ngôn ngữ người dùng (pl dùng tiếng Anh). Thiếu / hỏng `public.pem` thì tự dùng `word_lib`.
- `Token`: thêm `meaning_source = "dict"`, `level` (JLPT), `han` (âm Hán Việt, chỉ tiếng Việt), `dict_id` (khuôn 1.4).
- Cache từng từ, hạn giờ 1,5 s / lần gọi, ngừng gọi 60 s sau 5 lỗi liên tiếp; từ không tra được thì LLM điền nghĩa.

**Đa ngôn ngữ**
- Bản dịch kho ngữ pháp (`grammar/grammar_text.<lang>.json`, hiện có en, ko): tên, nhãn ngắn, ý nghĩa, cách nối, giải thích, ghi chú, câu ví dụ, lỗi thường gặp, bảng so sánh. Thiếu bản dịch thì dùng tiếng Việt. Đưa một ngôn ngữ vào bằng `scripts/translation/publish_lang.py <lang>`.
- `GrammarDetail.examples[].tr`: câu ví dụ dịch theo `lang` (chưa có thì bằng `vi`) - khuôn 1.5. `text_lang` cho biết phần chữ đang ở ngôn ngữ nào.
- Mẫu trùng đã gộp dùng nội dung và nhãn đã dịch của mẫu chuẩn.
- Bảng trợ từ dịch sẵn en, id, tw, cn, ko (`tables/particle_table.<lang>.json`); đổi bảng là đổi khoá cache.
- `labels(lang)`: nhãn cho mã trong kết quả (từ loại, nhóm động từ, vai trò, loại mệnh đề, trạng thái câu, mã lỗi), 16 ngôn ngữ; ngôn ngữ chưa có dùng tiếng Anh.

**Khác**
- `check_ready(settings=None, ping=False)`: kiểm tra kho, tách từ, LLM, cache, từ điển khi khởi động.
- Trang test: nhãn và câu ví dụ theo ngôn ngữ kết quả; thêm `/api/labels`, `/api/ready`.

## 0.1.0

Bản đầu: tách từ, tra `word_lib`, dò mẫu ngữ pháp bằng luật (N5–N1), LLM dựng cấu trúc câu, kiểm tra câu sai, cache + dịch nhẹ, `grammar_detail()` (khuôn kết quả 1.3).
