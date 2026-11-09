"""Cau hinh chung cho test: khong goi mang that.

Mac dinh module tra nghia tu bang Mazii (can mang); test dung kho word_lib tru khi tu truyen
dict_provider="mazii" (test_dictionary dung du lieu mau, khong goi mang).
"""

import os

os.environ["BUNPO_DICT_PROVIDER"] = "kho"
