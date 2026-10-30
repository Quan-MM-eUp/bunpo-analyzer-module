# Lỗi dữ liệu kho phát hiện khi viết luật (bước 1.2 – 1.5d)

Tổng hợp để chuyển team nội dung. Số là `id` trong `grammar_lib.json`. Module hiển thị kho nguyên trạng, nên sửa ở kho là giao diện tự cập nhật.

## 1. Câu ví dụ gõ sai

| ID | Mẫu | Lỗi |
|---|---|---|
| 265 | — | 「どんなにきらうでも」 |
| 271 | ～と言っていました | 「お弁当を行きますよ」 |
| 530 | ～ことに | 「うれしこいとに」 → うれしいことに |
| 536 | ～しかない | 「買しかなかった」 thiếu う |
| 560 | — | 「怒るものしかたがない」 → 怒るのも |
| 570 | ～とおり（に） | 「聞いていたとり」 |
| 698 | ～というとのに | Tên mẫu và cả 3 câu ví dụ viết 「というとのに」 (đúng: というのに) |
| 747 | — | Tên mẫu 「～もし休みがたとしても」 |
| 751 | — | 「買うしなかった」 → 買うしかなかった |
| 794 | — | 「買い物に行きつもりでした」 thiếu く |
| 799 | — | 「遅れるれる」 lặp chữ |
| 886 | — | 「こうだね」 (có lẽ そうだね) |
| 923 | ～ずじまい | 「原稿を書かければならくて」 |
| 927 | ～だけに | 「苦しい試合だっただけいに、、」 |
| 957 | — | 「懐疑」 (đúng: 会議) |
| 964 | ～にこしたことはない | 「にこしことはない」 thiếu た |
| 981 | — | 「初列する」, 「あの人の男」 |
| 984 | — | 「縮退をして」 |
| 1007 | ～ものの | 「泣かなやめられない」 |
| 1015 | — | 「相談た上で」, 「なけらば」 |
| 1021 | — | 「受験すことにした」 thiếu る |
| 1026 | — | Tên mẫu 「（よ）うあ～まいか」 |
| 1060 | — | Tên mẫu 「ことか／どろう」 (đúng: だろう) |
| 1062 | — | 「毎日のこことなると」 dư こ |
| 1071 | — | 「彼女のとこが」 (đúng: こと) |
| 1138 | — | 「泣かんか仕事が見つからない」, 「病気へ行こうにも」 |
| 1226 | — | 「お話し中ところを」 thiếu の |
| 1262 | ～んがために | 「生き残りんがために」 → 生き残らん |
| 1337 | — | 「惨惨しくて」 |
| 1379 | ～べからず | 「ここでの喫煙するべからず」 |

## 2. Câu ví dụ lẫn mẫu khác / không chứa mẫu

48, 339, 345, 371, 430, 504, 536, 540, 565, 574, 609, 705, 706, 710, 711, 729, 741, 749, 755, 756, 760, 783, 795, 924, 930, 1022, 1090 (động từ 抜く), 1221, 1300, 1320, 1333, 1351.

## 3. Câu ví dụ chèn ghi chú / cách đọc giữa câu

Ví dụ `会議中（ちゅう）`, `[⇔…]`, `（/こと）`, `（≒…）`: 320, 322, 323, 420, 439, 614, 647, 650, 787, 1012, 1118, 1137. Mẫu 1117 có dòng liệt kê kiểu "・宗教上理由 ・金銭上…", không phải câu.

## 4. Mẫu chưa có câu ví dụ

1522, 1523, 1528, 1532, 1536, 1537, 1539, 1540, 1541, 1543, 1545, 1546, 1550, 1553, 1556, 1558, 1559, 1562, 1574, 1576, 1578, 1585, 1586, 1587, 1594, 1604. Luật đã tự soạn câu ví dụ.

## 5. Nghĩa (`meaning_vi`) / `接続` / tên mẫu có vấn đề

- `meaning_vi` chứa câu ví dụ kèm `#####` thay vì nghĩa: 1588–1593, 1598–1602.
- Nghĩa sai hoặc mơ hồ: 1544 (ghi "sự cần thiết, nghĩa vụ", thực ra là "chẳng cần phải…"), 1595 ("mức cực đoan"), 1535 ("Diễn đạt vô can").
- `接続` ghi nhầm: 622 (～上げる ghi 「N1はN2にN3をあげる」), 1041 (từ nối したがって ghi 「Vるにしたがって」).
- Tên mẫu dính các biến thể, không có dấu ngăn cách: 1403, 1405, 1407, 1420, 1431, 1439, 1457, 1479.

## 6. Mẫu trùng nội dung

Ví dụ: ている (136/234), ようになる (381/431/613/1608), 真っ (486/1604), や否や (1497/1584), ようが…まいが (1499/1500/1502/1522), べからず (1379/1403), びる (1360/1405), 皮切りに (1391/1392). Mỗi id vẫn có luật riêng nên một câu có thể ra nhiều ứng viên giống nhau. Đề xuất chọn một mẫu "chuẩn" cho mỗi nhóm (mục 3.3 file kế hoạch).

## 7. Từ vựng cơ bản thiếu trong word_lib (bước 1.4)

なる (chỉ có 鳴る), いる (chỉ có 要る), よく, 大きな, 小さな, そんな, こんな, あんな, どんな, 履く, 人々, 気. Module đang bổ sung tạm trong `tables/particle_table.json` (các mục `core`).

## 8. Mục gộp nhiều mẫu cũ (bước 3.1)

321/1.621 mục có nhiều khối câu ví dụ ngăn bằng dòng `──────`; các khối sau thường là nghĩa / mẫu khác bị gộp vào. Ví dụ:

- #159 なる: gộp cả "Naで～", "Naじゃない", "Naに V".
- #173 ～と (điều kiện): có khối ví dụ "と = cùng với" (母と富士山に登ります).
- #193 ～を (qua nơi chốn): có khối "を tân ngữ" (マンガを読みます).

Khi chấm, module chỉ dùng khối đầu làm nghĩa chính. Bộ luật bắt được 78–95% câu ở các khối gộp tuỳ cấp (N5 thấp nhất).

Một số câu ví dụ ở khối chính không chứa mẫu của mục (thuộc mẫu khác): #761 (câu ために), #265 (câu ～ば), #339 (câu hỏi tu từ). Một số câu gõ sai: #570 「聞いていたとり」, #716 「統計によるば」, #751 「買うしなかった」, #560 「怒るものしかたがない」. LLM cũng báo đúng 2 câu gõ sai: #443 「旅行に行きので」 (đúng: 行くので), #1542 「食ベなくても」 (chữ ベ katakana).

Xem đủ danh sách: `python scripts/eval.py --rules-only --levels N5 N4 N3 N2 N1`, rồi mở `runs/rules_miss_<cấp>.txt` (khối chính) và `runs/rules_miss_<cấp>_gop.txt` (khối gộp).
