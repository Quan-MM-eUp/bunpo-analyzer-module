"""bunpo_analyzer: phan tich ngu phap mot cau tieng Nhat.

Ben ngoai goi `analyze()` (muc 11.2), `grammar_detail()` cho bang ngu phap (muc 11.7) va `labels(lang)` lay
nhan giao dien cho cac ma trong ket qua; `check_ready()` kiem tra cau hinh khi khoi dong.
"""

from bunpo_analyzer.config import Settings, get_settings
from bunpo_analyzer.core.analyzer import analyze
from bunpo_analyzer.core.grammar_detail import GrammarDetail, grammar_detail
from bunpo_analyzer.core.labels import label_langs, labels
from bunpo_analyzer.core.ready import check_ready
from bunpo_analyzer.schema import SCHEMA_VERSION, AnalysisResult

__version__ = "0.2.1"

__all__ = ["analyze", "grammar_detail", "GrammarDetail", "labels", "label_langs", "check_ready", "AnalysisResult",
           "SCHEMA_VERSION", "Settings", "get_settings", "__version__"]
