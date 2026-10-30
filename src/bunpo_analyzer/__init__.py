"""bunpo_analyzer: phan tich ngu phap mot cau tieng Nhat.

Ben ngoai goi `analyze()` (muc 11.2) va `grammar_detail()` cho bang ngu phap (muc 11.7).
"""

from bunpo_analyzer.config import Settings, get_settings
from bunpo_analyzer.core.analyzer import analyze
from bunpo_analyzer.core.grammar_detail import GrammarDetail, grammar_detail
from bunpo_analyzer.schema import SCHEMA_VERSION, AnalysisResult

__version__ = "0.1.0"

__all__ = ["analyze", "grammar_detail", "GrammarDetail", "AnalysisResult", "SCHEMA_VERSION", "Settings", "get_settings", "__version__"]
