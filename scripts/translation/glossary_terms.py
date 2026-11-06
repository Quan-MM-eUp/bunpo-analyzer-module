"""C2: danh sach thuat ngu nguon (tieng Viet) cho bang thuat ngu 15 ngon ngu.

    python glossary_terms.py --ws <translation/> [--min 0]

Ghi glossary/_source.json: moi thuat ngu {id, cat, vi[], ja, hint, freq}. vi[0] la cach goi chinh,
cac bien the sau de check.py nhan ra trong ban nguon (so khop khong phan biet hoa thuong).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_json, workspace, write_json

# (id, nhom, [bien the tieng Viet], tieng Nhat, goi y tieng Anh)
TERMS: list[tuple[str, str, list[str], str, str]] = [
    # ---- tu loai ----
    ("noun", "pos", ["danh từ"], "名詞", "noun"),
    ("verb", "pos", ["động từ"], "動詞", "verb"),
    ("adjective", "pos", ["tính từ"], "形容詞", "adjective"),
    ("i_adj", "pos", ["tính từ đuôi い", "tính từ い"], "い形容詞", "i-adjective"),
    ("na_adj", "pos", ["tính từ đuôi な", "tính từ な"], "な形容詞", "na-adjective"),
    ("adverb", "pos", ["phó từ", "trạng từ"], "副詞", "adverb"),
    ("particle", "pos", ["trợ từ"], "助詞", "particle"),
    ("aux_verb", "pos", ["trợ động từ"], "助動詞", "auxiliary verb"),
    ("conjunction", "pos", ["liên từ", "từ nối"], "接続詞", "conjunction / connective"),
    ("interrogative", "pos", ["từ để hỏi", "nghi vấn từ"], "疑問詞", "question word"),
    ("pronoun", "pos", ["đại từ"], "代名詞", "pronoun"),
    ("demonstrative", "pos", ["từ chỉ thị", "đại từ chỉ thị"], "指示詞", "demonstrative (ko-so-a-do words)"),
    ("counter", "pos", ["trợ số từ", "lượng từ"], "助数詞", "counter word"),
    ("numeral", "pos", ["số từ"], "数詞", "numeral"),
    ("onomatopoeia", "pos", ["từ tượng thanh", "từ tượng hình", "từ láy"], "オノマトペ", "onomatopoeia / mimetic word"),
    ("interjection", "pos", ["thán từ"], "感動詞", "interjection"),
    ("suffix", "pos", ["hậu tố"], "接尾辞", "suffix"),
    ("prefix", "pos", ["tiền tố"], "接頭辞", "prefix"),
    ("compound", "pos", ["từ ghép"], "複合語", "compound word"),
    ("compound_verb", "pos", ["động từ ghép"], "複合動詞", "compound verb"),
    ("noun_phrase", "pos", ["cụm danh từ"], "名詞句", "noun phrase"),
    ("nominalization", "pos", ["danh từ hóa", "danh từ hoá"], "名詞化", "nominalization"),
    ("abstract_noun", "pos", ["danh từ trừu tượng"], "抽象名詞", "abstract noun"),
    ("formal_noun", "pos", ["danh từ hình thức"], "形式名詞", "formal noun (こと, もの, ところ...)"),
    ("time_noun", "pos", ["danh từ chỉ thời gian"], "時間名詞", "noun of time"),
    ("place_noun", "pos", ["danh từ chỉ địa điểm", "danh từ chỉ nơi chốn"], "場所名詞", "noun of place"),
    ("person_noun", "pos", ["danh từ chỉ người"], "人を表す名詞", "noun denoting a person"),
    ("verbal_noun", "pos", ["danh động từ", "danh từ する"], "サ変名詞", "verbal noun (noun + する)"),
    ("sino_word", "pos", ["từ hán", "hán ngữ"], "漢語", "Sino-Japanese word"),
    # ---- tro tu ----
    ("case_particle", "particle", ["trợ từ cách"], "格助詞", "case particle"),
    ("conj_particle", "particle", ["trợ từ liên kết", "trợ từ nối"], "接続助詞", "conjunctive particle"),
    ("adv_particle", "particle", ["trợ từ phó", "phó trợ từ"], "副助詞", "adverbial particle"),
    ("final_particle", "particle", ["trợ từ cuối câu", "trợ từ kết thúc câu"], "終助詞", "sentence-final particle"),
    ("topic_particle", "particle", ["trợ từ chủ đề"], "係助詞「は」", "topic particle"),
    # ---- loai dong tu ----
    ("verb_g1", "verb", ["động từ nhóm 1", "động từ nhóm i", "nhóm 1"], "五段動詞（Iグループ）", "Group 1 verb (godan / u-verb)"),
    ("verb_g2", "verb", ["động từ nhóm 2", "động từ nhóm ii", "nhóm 2"], "一段動詞（IIグループ）", "Group 2 verb (ichidan / ru-verb)"),
    ("verb_g3", "verb", ["động từ nhóm 3", "động từ nhóm iii", "nhóm 3"], "不規則動詞（IIIグループ）", "Group 3 verb (irregular: する, 来る)"),
    ("intransitive", "verb", ["tự động từ"], "自動詞", "intransitive verb"),
    ("transitive", "verb", ["tha động từ"], "他動詞", "transitive verb"),
    ("motion_verb", "verb", ["động từ chuyển động", "động từ di chuyển"], "移動動詞", "verb of motion"),
    ("state_verb", "verb", ["động từ trạng thái", "động từ chỉ trạng thái"], "状態動詞", "stative verb"),
    ("action_verb", "verb", ["động từ hành động", "động từ chỉ hành động"], "動作動詞", "action verb"),
    ("change_verb", "verb", ["động từ biến đổi", "động từ chỉ sự thay đổi"], "変化動詞", "verb of change"),
    ("perception_verb", "verb", ["động từ tri giác"], "知覚動詞", "verb of perception"),
    ("volitional_verb", "verb", ["động từ ý chí", "động từ có ý chí"], "意志動詞", "volitional verb"),
    ("nonvolitional_verb", "verb", ["động từ vô ý chí", "động từ không ý chí"], "無意志動詞", "non-volitional verb"),
    ("speech_verb", "verb", ["động từ phát ngôn", "động từ nói năng"], "発話動詞", "verb of speaking"),
    ("giving_receiving", "verb", ["động từ cho nhận", "cho nhận"], "授受動詞", "giving and receiving verbs (あげる, くれる, もらう)"),
    ("aux_verb_hojo", "verb", ["động từ bổ trợ"], "補助動詞", "subsidiary verb (～ている, ～てみる...)"),
    ("continuative_verb", "verb", ["động từ kéo dài", "động từ liên tục"], "継続動詞", "durative verb"),
    ("instant_verb", "verb", ["động từ tức thời", "động từ khoảnh khắc"], "瞬間動詞", "punctual verb"),
    # ---- the / dang ----
    ("form", "form", ["thể", "dạng"], "形", "form (verb form / conjugated form)"),
    ("conjugation", "form", ["chia động từ", "cách chia", "biến đổi"], "活用", "conjugation"),
    ("dict_form", "form", ["thể từ điển", "nguyên dạng", "thể nguyên dạng"], "辞書形", "dictionary form"),
    ("masu_form", "form", ["thể ます", "dạng ます"], "ます形", "masu-form"),
    ("masu_stem", "form", ["thể ます bỏ ます", "gốc động từ", "thân động từ"], "ます形の語幹", "masu-stem (verb stem)"),
    ("nai_form", "form", ["thể ない", "dạng ない"], "ない形", "nai-form (negative form)"),
    ("te_form", "form", ["thể て", "dạng て"], "て形", "te-form"),
    ("ta_form", "form", ["thể た", "dạng た"], "た形", "ta-form (past form)"),
    ("plain_form", "form", ["thể thường", "thể thông thường", "thể ngắn"], "普通形", "plain form"),
    ("polite_form", "form", ["thể lịch sự", "dạng lịch sự", "thể です・ます"], "丁寧形", "polite form (desu/masu)"),
    ("volitional_form", "form", ["thể ý chí", "thể ý hướng"], "意向形", "volitional form"),
    ("potential_form", "form", ["thể khả năng"], "可能形", "potential form"),
    ("passive_form", "form", ["thể bị động", "bị động"], "受身形", "passive form"),
    ("causative_form", "form", ["thể sai khiến", "sai khiến"], "使役形", "causative form"),
    ("causative_passive", "form", ["thể bị động sai khiến", "thể sai khiến bị động", "bị động sai khiến"], "使役受身形", "causative-passive form"),
    ("imperative_form", "form", ["thể mệnh lệnh"], "命令形", "imperative form"),
    ("prohibitive_form", "form", ["thể cấm chỉ", "thể cấm đoán"], "禁止形", "prohibitive form"),
    ("ba_form", "form", ["thể điều kiện", "thể ば", "thể giả định"], "仮定形（ば形）", "conditional ba-form"),
    ("tara_form", "form", ["thể たら", "dạng たら"], "たら形", "tara-form"),
    ("tai_form", "form", ["thể たい", "dạng たい"], "たい形", "tai-form (desire)"),
    ("te_iru", "form", ["thể ている", "dạng ている"], "ている形", "te-iru form"),
    ("renyo", "form", ["thể liên dụng", "liên dụng"], "連用形", "continuative form (ren'yōkei)"),
    ("rentai", "form", ["thể liên thể", "liên thể", "dạng bổ nghĩa danh từ"], "連体形", "attributive form (rentaikei)"),
    ("contracted_form", "form", ["dạng rút gọn", "thể rút gọn", "cách nói rút gọn"], "縮約形", "contracted form"),
    ("affirmative_form", "form", ["thể khẳng định", "dạng khẳng định"], "肯定形", "affirmative form"),
    ("negative_form", "form", ["thể phủ định", "dạng phủ định"], "否定形", "negative form"),
    ("past_form", "form", ["thể quá khứ", "dạng quá khứ"], "過去形", "past form"),
    ("nonpast_form", "form", ["thể phi quá khứ", "phi quá khứ"], "非過去形", "non-past form"),
    ("stem", "form", ["gốc", "phần gốc", "thân từ"], "語幹", "stem"),
    ("ending", "form", ["đuôi", "phần đuôi"], "語尾", "ending"),
    # ---- thi, the cach, phu dinh ----
    ("tense", "tam", ["thì"], "時制", "tense"),
    ("present", "tam", ["hiện tại", "thì hiện tại"], "現在", "present"),
    ("past", "tam", ["quá khứ", "thì quá khứ"], "過去", "past"),
    ("future", "tam", ["tương lai", "thì tương lai"], "未来", "future"),
    ("progressive", "tam", ["tiếp diễn", "đang diễn ra"], "進行", "progressive / ongoing action"),
    ("perfective", "tam", ["hoàn thành", "hoàn tất"], "完了", "completion / perfective"),
    ("resultant_state", "tam", ["trạng thái kết quả", "kết quả còn lưu lại"], "結果の状態", "resultant state"),
    ("habit", "tam", ["thói quen", "hành động lặp lại"], "習慣", "habit / repeated action"),
    ("experience", "tam", ["kinh nghiệm", "trải nghiệm"], "経験", "experience"),
    ("affirmative", "tam", ["khẳng định"], "肯定", "affirmative"),
    ("negative", "tam", ["phủ định"], "否定", "negative / negation"),
    ("double_negative", "tam", ["phủ định kép"], "二重否定", "double negative"),
    ("partial_negation", "tam", ["phủ định một phần", "phủ định bộ phận"], "部分否定", "partial negation"),
    ("total_negation", "tam", ["phủ định toàn phần", "phủ định hoàn toàn"], "全部否定", "total negation"),
    ("strong_negation", "tam", ["phủ định mạnh", "phủ định tuyệt đối"], "強い否定", "strong / absolute negation"),
    ("interrogative_mood", "tam", ["nghi vấn"], "疑問", "interrogative"),
    ("rhetorical_question", "tam", ["câu hỏi tu từ", "phản vấn"], "反語", "rhetorical question"),
    # ---- y nghia / chuc nang ----
    ("condition", "func", ["điều kiện"], "条件", "condition"),
    ("hypothetical", "func", ["giả định", "giả thiết"], "仮定", "hypothesis / supposition"),
    ("hypothetical_condition", "func", ["điều kiện giả định"], "仮定条件", "hypothetical condition"),
    ("counterfactual", "func", ["trái với thực tế", "phản thực tế", "giả định ngược"], "反実仮想", "counterfactual"),
    ("adversative", "func", ["nghịch tiếp", "ngược lại với dự đoán", "trái ngược"], "逆接", "adversative (contrary to expectation)"),
    ("concession", "func", ["nhượng bộ"], "譲歩", "concession"),
    ("cause_reason", "func", ["nguyên nhân", "lý do", "nguyên nhân lý do"], "原因・理由", "cause / reason"),
    ("purpose", "func", ["mục đích"], "目的", "purpose"),
    ("result", "func", ["kết quả"], "結果", "result"),
    ("comparison", "func", ["so sánh"], "比較", "comparison"),
    ("contrast", "func", ["đối lập", "đối chiếu", "tương phản"], "対比", "contrast"),
    ("listing", "func", ["liệt kê"], "列挙", "listing / enumeration"),
    ("example_giving", "func", ["nêu ví dụ", "đưa ví dụ", "lấy ví dụ"], "例示", "giving examples"),
    ("conjecture", "func", ["phỏng đoán", "suy đoán", "suy luận"], "推量", "conjecture / inference"),
    ("hearsay", "func", ["truyền đạt", "nghe nói", "truyền văn"], "伝聞", "hearsay / reported information"),
    ("appearance", "func", ["dáng vẻ", "trông có vẻ", "có vẻ"], "様態", "appearance (looks like)"),
    ("obligation", "func", ["nghĩa vụ", "bắt buộc"], "義務", "obligation"),
    ("permission", "func", ["cho phép", "sự cho phép"], "許可", "permission"),
    ("prohibition", "func", ["cấm đoán", "cấm chỉ", "sự cấm đoán"], "禁止", "prohibition"),
    ("advice", "func", ["khuyên bảo", "lời khuyên"], "助言", "advice"),
    ("suggestion", "func", ["đề nghị", "đề xuất"], "提案", "suggestion / proposal"),
    ("invitation", "func", ["mời rủ", "lời mời", "rủ rê"], "勧誘", "invitation"),
    ("request", "func", ["nhờ vả", "yêu cầu", "lời nhờ"], "依頼", "request"),
    ("command", "func", ["mệnh lệnh"], "命令", "command / order"),
    ("desire", "func", ["mong muốn", "nguyện vọng", "ước muốn"], "希望・願望", "desire / wish"),
    ("intention", "func", ["ý định", "dự định"], "意図・予定", "intention / plan"),
    ("volition", "func", ["ý chí"], "意志", "will / volition"),
    ("ability", "func", ["khả năng", "năng lực"], "可能", "ability / possibility"),
    ("exclamation", "func", ["cảm thán"], "感嘆", "exclamation"),
    ("emphasis", "func", ["nhấn mạnh"], "強調", "emphasis"),
    ("limitation", "func", ["giới hạn", "hạn định"], "限定", "limitation (only)"),
    ("degree", "func", ["mức độ"], "程度", "degree / extent"),
    ("scope", "func", ["phạm vi"], "範囲", "range / scope"),
    ("target", "func", ["đối tượng"], "対象", "target / object of an action or feeling"),
    ("means", "func", ["phương tiện", "cách thức", "phương pháp"], "手段・方法", "means / method"),
    ("agent", "func", ["tác nhân", "chủ thể hành động", "chủ thể"], "動作主", "agent / doer"),
    ("starting_point", "func", ["điểm xuất phát", "khởi điểm"], "起点", "starting point"),
    ("destination", "func", ["đích đến", "điểm đến", "hướng đến"], "着点・方向", "destination / direction"),
    ("time_point", "func", ["thời điểm"], "時点", "point in time"),
    ("simultaneity", "func", ["đồng thời", "cùng lúc"], "同時", "simultaneous actions"),
    ("sequence", "func", ["trình tự", "thứ tự hành động", "nối tiếp"], "継起", "sequence of actions"),
    ("addition", "func", ["bổ sung", "thêm vào"], "添加", "addition (moreover)"),
    ("topic_change", "func", ["chuyển chủ đề", "đổi chủ đề"], "話題転換", "change of topic"),
    ("evaluation", "func", ["đánh giá", "nhận xét"], "評価", "evaluation / judgment"),
    ("criticism", "func", ["phê phán", "chê trách", "trách móc"], "非難", "criticism / reproach"),
    ("regret", "func", ["hối hận", "tiếc nuối"], "後悔・残念", "regret"),
    ("surprise", "func", ["ngạc nhiên", "bất ngờ"], "驚き", "surprise"),
    ("certainty", "func", ["chắc chắn", "khẳng định chắc chắn"], "確信", "certainty / conviction"),
    ("tendency", "func", ["khuynh hướng", "xu hướng"], "傾向", "tendency"),
    ("change_state", "func", ["sự thay đổi", "biến đổi trạng thái"], "変化", "change"),
    # ---- cu phap ----
    ("subject", "syntax", ["chủ ngữ"], "主語", "subject"),
    ("predicate", "syntax", ["vị ngữ"], "述語", "predicate"),
    ("object", "syntax", ["tân ngữ"], "目的語", "object"),
    ("complement", "syntax", ["bổ ngữ"], "補語", "complement"),
    ("topic", "syntax", ["chủ đề"], "主題", "topic"),
    ("modifier", "syntax", ["bổ nghĩa", "từ bổ nghĩa"], "修飾", "modification / modifier"),
    ("clause", "syntax", ["mệnh đề", "vế câu", "vế"], "節", "clause"),
    ("main_clause", "syntax", ["mệnh đề chính", "vế chính"], "主節", "main clause"),
    ("sub_clause", "syntax", ["mệnh đề phụ", "vế phụ"], "従属節", "subordinate clause"),
    ("first_clause", "syntax", ["mệnh đề trước", "vế trước", "vế đầu"], "前件", "first clause (preceding part)"),
    ("second_clause", "syntax", ["mệnh đề sau", "vế sau"], "後件", "second clause (following part)"),
    ("relative_clause", "syntax", ["mệnh đề quan hệ", "mệnh đề bổ nghĩa danh từ"], "連体修飾節", "noun-modifying clause"),
    ("sentence", "syntax", ["câu", "câu văn"], "文", "sentence"),
    ("sentence_end", "syntax", ["cuối câu"], "文末", "end of a sentence"),
    ("sentence_start", "syntax", ["đầu câu"], "文頭", "beginning of a sentence"),
    ("question_sentence", "syntax", ["câu hỏi", "câu nghi vấn"], "疑問文", "question"),
    ("answer", "syntax", ["câu trả lời"], "答え", "answer"),
    ("affirmative_sentence", "syntax", ["câu khẳng định"], "肯定文", "affirmative sentence"),
    ("negative_sentence", "syntax", ["câu phủ định"], "否定文", "negative sentence"),
    ("quotation", "syntax", ["trích dẫn", "dẫn lời"], "引用", "quotation"),
    ("inversion", "syntax", ["đảo ngữ", "đảo trật tự"], "倒置", "inversion"),
    ("omission", "syntax", ["lược bỏ", "tỉnh lược"], "省略", "omission / ellipsis"),
    ("context", "syntax", ["ngữ cảnh", "văn cảnh"], "文脈", "context"),
    ("structure", "meta", ["cấu trúc"], "構文", "structure / construction"),
    ("sentence_pattern", "meta", ["mẫu câu"], "文型", "sentence pattern"),
    ("grammar_pattern", "meta", ["mẫu ngữ pháp", "ngữ pháp", "mẫu"], "文法項目", "grammar point / pattern"),
    ("connection", "meta", ["cách nối", "cách kết hợp", "kết hợp với"], "接続", "how it connects (formation)"),
    ("usage", "meta", ["cách dùng", "cách sử dụng", "dùng khi"], "用法", "usage"),
    ("meaning", "meta", ["ý nghĩa", "nghĩa"], "意味", "meaning"),
    ("nuance", "meta", ["sắc thái"], "ニュアンス", "nuance"),
    ("difference", "meta", ["khác biệt", "điểm khác", "điểm khác biệt", "khác biệt chính"], "違い", "difference / key difference"),
    ("similarity", "meta", ["điểm giống", "điểm tương đồng", "tương quan"], "共通点", "similarity"),
    ("short_example", "meta", ["ví dụ ngắn"], "短い例文", "short example"),
    ("example", "meta", ["ví dụ", "câu ví dụ"], "例文", "example"),
    ("common_mistake", "meta", ["lỗi sai thường gặp", "lỗi thường gặp", "lỗi sai"], "よくある間違い", "common mistake"),
    ("note", "meta", ["lưu ý", "chú ý", "ghi chú"], "注意", "note"),
    ("correct", "meta", ["đúng"], "正しい", "correct (○)"),
    ("incorrect", "meta", ["sai"], "誤り", "incorrect (×)"),
    ("unnatural", "meta", ["không tự nhiên", "thiếu tự nhiên"], "不自然", "unnatural"),
    ("natural", "meta", ["tự nhiên"], "自然", "natural"),
    ("fixed_expression", "meta", ["cách nói cố định", "thành ngữ", "quán dụng ngữ"], "慣用表現", "set phrase / idiom"),
    ("expression", "meta", ["cách diễn đạt", "cách nói", "biểu hiện"], "表現", "expression"),
    # ---- van phong ----
    ("spoken", "register", ["văn nói", "khẩu ngữ"], "話し言葉", "spoken language / colloquial"),
    ("written", "register", ["văn viết"], "書き言葉", "written language"),
    ("formal_written", "register", ["văn viết trang trọng", "văn viết cứng"], "硬い書き言葉", "formal written style"),
    ("casual_spoken", "register", ["văn nói thân mật", "thân mật"], "くだけた話し言葉", "casual / informal speech"),
    ("formal", "register", ["trang trọng", "cứng nhắc", "văn cứng"], "改まった・硬い", "formal / stiff"),
    ("polite", "register", ["lịch sự"], "丁寧", "polite"),
    ("very_polite", "register", ["lịch sự cao", "rất lịch sự"], "非常に丁寧", "very polite"),
    ("keigo", "register", ["kính ngữ"], "敬語", "honorific language (keigo)"),
    ("sonkeigo", "register", ["tôn kính ngữ", "tôn kính"], "尊敬語", "respectful language (sonkeigo)"),
    ("kenjougo", "register", ["khiêm nhường ngữ", "khiêm nhường"], "謙譲語", "humble language (kenjōgo)"),
    ("teineigo", "register", ["từ lịch sự", "thể lịch sự teineigo"], "丁寧語", "polite language (teineigo)"),
    ("euphemism", "register", ["uyển ngữ", "nói giảm nói tránh", "mềm mỏng", "uyển chuyển"], "婉曲", "softened / indirect expression"),
    ("archaic", "register", ["cổ ngữ", "văn cổ", "cách nói cổ"], "古語・文語", "archaic / literary"),
    ("business", "register", ["văn công việc", "kinh doanh", "văn thư"], "ビジネス", "business context"),
    ("male_speech", "register", ["nam giới", "giọng nam"], "男性語", "male speech"),
    ("female_speech", "register", ["nữ giới", "giọng nữ"], "女性語", "female speech"),
    ("speaker", "register", ["người nói"], "話し手", "speaker"),
    ("listener", "register", ["người nghe"], "聞き手", "listener"),
    ("superior", "register", ["người trên", "cấp trên"], "目上の人", "social superior"),
    ("inferior", "register", ["người dưới", "cấp dưới"], "目下の人", "social inferior / junior"),
    ("third_person", "register", ["ngôi thứ ba", "người thứ ba"], "第三者", "third person"),
    ("first_person", "register", ["ngôi thứ nhất"], "一人称", "first person"),
    ("negative_nuance", "register", ["sắc thái tiêu cực", "nghĩa tiêu cực", "tiêu cực"], "マイナス評価", "negative nuance"),
    ("positive_nuance", "register", ["sắc thái tích cực", "nghĩa tích cực", "tích cực"], "プラス評価", "positive nuance"),
    ("subjective", "register", ["chủ quan"], "主観的", "subjective"),
    ("objective", "register", ["khách quan"], "客観的", "objective"),
    ("feeling", "register", ["cảm xúc", "tình cảm"], "感情", "feeling / emotion"),
]


# Thuat ngu chung chung / da nghia (thi, cau, sai, nghia...): van dich thong nhat nhung check.py khong do
NO_CHECK_CATS = {"func", "meta", "tam"}
NO_CHECK_IDS = {"form", "conjugation", "stem", "ending", "sentence", "context", "modifier", "topic", "clause",
                "speaker", "listener", "feeling", "subjective", "objective", "business", "male_speech",
                "female_speech", "formal", "polite", "casual_spoken", "negative_nuance", "positive_nuance",
                "superior", "inferior", "third_person", "first_person", "agent", "compound"}
CHECK_EXTRA = {"passive_form", "causative_form"}  # khang dinh / phu dinh / qua khu da nghia: khong do


def checked(tid: str, cat: str) -> bool:
    return tid in CHECK_EXTRA or (cat not in NO_CHECK_CATS and tid not in NO_CHECK_IDS)


def count_freq(items: dict) -> dict[str, int]:
    texts = []
    for it in items.values():
        for k, v in it["fields"].items():
            if isinstance(v, dict) and "text" in v and v["src"] == "vi":
                texts.append(v["text"])
            elif k == "mistakes":
                texts += [m["text"] for m in v if m["src"] == "vi"]
            elif k == "comparison":
                texts += v["headers"] + [c for r in v["rows"] for c in r]
    t = "\n".join(texts).lower()
    out = {}
    for tid, _, vis, _, _ in TERMS:
        out[tid] = sum(len(re.findall(r"(?<![\wà-ỹđ])" + re.escape(v) + r"(?![\wà-ỹđ])", t)) for v in vis)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws")
    a = ap.parse_args(argv)
    ws = workspace(a.ws)
    ids = [t[0] for t in TERMS]
    assert len(ids) == len(set(ids)), "trung id"
    freq = count_freq(read_json(ws / "source" / "items.json"))
    terms = [{"id": tid, "cat": cat, "vi": vis, "ja": ja, "hint": hint, "freq": freq[tid],
              "check": checked(tid, cat)}
             for tid, cat, vis, ja, hint in TERMS]
    write_json(ws / "glossary" / "_source.json", {"version": "1", "terms": terms})
    print(f"{len(terms)} thuat ngu; khong xuat hien: {[t['id'] for t in terms if not t['freq']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
