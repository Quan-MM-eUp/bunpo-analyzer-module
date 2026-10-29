"""bunpo_analyzer: phan tich ngu phap mot cau tieng Nhat.

Ben ngoai chi can goi `analyze()` (muc 11.2 file ke hoach).
"""

from bunpo_analyzer.config import Settings, get_settings
from bunpo_analyzer.core.analyzer import analyze
from bunpo_analyzer.schema import SCHEMA_VERSION, AnalysisResult

__version__ = "0.1.0"

__all__ = ["analyze", "AnalysisResult", "SCHEMA_VERSION", "Settings", "get_settings", "__version__"]
