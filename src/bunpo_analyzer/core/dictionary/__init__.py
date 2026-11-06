"""Tu dien tra nghia tu (thay kho word_lib): Mazii API, co cache, gioi han thoi gian, ngat tam khi loi.

Chon bang `Settings.dict_provider`: "kho" (word_lib, mac dinh, khong can mang) | "mazii".
"""

from bunpo_analyzer.core.dictionary.base import DictEntry, Dictionary, Sense
from bunpo_analyzer.core.dictionary.mazii import (
    MAZII_DICTS,
    MaziiDictionary,
    decrypt_payload,
    derive_key,
)

__all__ = ["MAZII_DICTS", "DictEntry", "Dictionary", "MaziiDictionary", "Sense", "decrypt_payload", "derive_key"]
