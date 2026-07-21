from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel


class Candidate(BaseModel):
    ticker: str
    rule: str
    trend_status: Optional[str] = None
    trend_strength: Optional[int] = None
    signal_score: Optional[int] = None
    vol_ratio: Optional[float] = None
    off_20d_high_pct: Optional[float] = None
    rsi6: Optional[float] = None
    entry_close: Optional[float] = None
    is_new: bool = False


class NominateResponse(BaseModel):
    session_date: str
    groups: Dict[str, List[Candidate]]


class HistoryItem(BaseModel):
    session_date: str
    rule: str
    entry_close: Optional[float] = None
    latest_close: Optional[float] = None
    return_pct: Optional[float] = None


class HistoryResponse(BaseModel):
    ticker: str
    calls: List[HistoryItem]


class TrackRecordRule(BaseModel):
    rule: str
    n: int
    mean_20d_pct: Optional[float] = None
    base_20d_pct: Optional[float] = None


class TrackRecordResponse(BaseModel):
    rules: List[TrackRecordRule]
