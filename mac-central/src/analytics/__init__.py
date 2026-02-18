"""Analytics module for Neuro-Pipeline.

Provides:
- reid_engine: Cross-camera re-identification
- timeseries_engine: Time series analysis and trend detection
- auto_annotator: Automatic annotation generation
- report_generator: Event report generation (moved from reporting/)
"""

from .reid_engine import ReIDEngine, ReIDMatch, ReIDTrack
from .timeseries_engine import TimeSeriesEngine, TrendResult, AnomalyPoint
from .auto_annotator import AutoAnnotator, AnnotatedSample
from .report_generator import ReportGenerator, EventReport, ReportSection

__all__ = [
    # ReID
    "ReIDEngine",
    "ReIDMatch",
    "ReIDTrack",
    # Time Series
    "TimeSeriesEngine",
    "TrendResult",
    "AnomalyPoint",
    # Auto Annotator
    "AutoAnnotator",
    "AnnotatedSample",
    # Report Generator
    "ReportGenerator",
    "EventReport",
    "ReportSection",
]
