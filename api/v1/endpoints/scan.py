"""$0 technical-signal scan endpoints. No LLM. Persists nominations at fire-time."""
from __future__ import annotations

import logging
import warnings
from typing import Dict, List

from fastapi import APIRouter, Query

from api.v1.schemas.scan import (Candidate, NominateResponse, HistoryItem,
                                 HistoryResponse, TrackRecordRule, TrackRecordResponse,
                                 ScreenRequest, ScreenResponse, ScreenRow)
from src.core.trading_calendar import get_effective_trading_date
from src.services.signal_screen import NDX_100, describe_one, screen_one
from src.services import signal_nomination_store as store
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()
_RULES = ("breakout", "oversold")


def _engine():
    return DatabaseManager.get_instance()._engine


def download_history(tickers: List[str]) -> Dict[str, object]:
    """Batch daily history for the universe. Isolated for test patching."""
    import yfinance as yf
    warnings.filterwarnings("ignore")
    raw = yf.download(tickers, period="6mo", interval="1d", group_by="ticker",
                      progress=False, threads=True, auto_adjust=True)
    out: Dict[str, object] = {}
    for t in tickers:
        try:
            df = raw[t].dropna().reset_index()
            df.columns = [str(c).lower() for c in df.columns]
            out[t] = df
        except Exception:
            continue
    return out


def _trim_to_session(df, session_date: str):
    """Drop any bar dated after session_date (the last COMPLETE session). Intraday,
    yfinance appends a forming daily bar; screening it makes /signals nominate on the
    live intraday price and flicker (e.g. an intraday RSI dip surfaces then vanishes).
    Screening only complete bars keeps the board stable and aligned with its date."""
    if df is None or "date" not in getattr(df, "columns", []):
        return df
    try:
        return df[df["date"].astype(str).str[:10] <= session_date]
    except Exception:
        return df


def _price_lookup_factory(history: Dict[str, object]):
    def lookup(ticker: str, session_date: str, horizon: int):
        df = history.get(ticker)
        if df is None or "date" not in df.columns:
            return None
        dates = [str(d)[:10] for d in df["date"]]
        if session_date not in dates:
            return None
        idx = dates.index(session_date) + horizon
        if idx >= len(df):
            return None
        return float(df["close"].iloc[idx])
    return lookup


def _prev_session(engine, session_date: str) -> str:
    """Most recent session_date strictly before the current one that has rows."""
    rows = store._rows(engine, "SELECT DISTINCT session_date FROM signal_nominations "
                       "WHERE session_date < :d ORDER BY session_date DESC LIMIT 1",
                       {"d": session_date})
    return rows[0]["session_date"] if rows else ""


@router.post("/screen", response_model=ScreenResponse)
def screen(request: ScreenRequest) -> ScreenResponse:
    """Describe an arbitrary ticker list. No LLM, no search, nothing persisted.

    Backs the bot's watchlist digest, which replaced a per-ticker /analyze that
    cost real money and then discarded most of what it bought. Every requested
    ticker gets a row unless it is untradeable or too new to measure -- a digest
    that drops a user's quiet names is not a digest.
    """
    tickers = [t.strip().upper() for t in request.tickers if t and t.strip()]
    if not tickers:
        return ScreenResponse(
            session_date=get_effective_trading_date("us").strftime("%Y-%m-%d"), rows=[])

    session_date = get_effective_trading_date("us").strftime("%Y-%m-%d")
    history = download_history(tickers)

    rows: List[ScreenRow] = []
    for ticker in tickers:
        df = history.get(ticker)
        if df is None:
            continue
        try:
            described = describe_one(_trim_to_session(df, session_date), ticker)
        except Exception:
            logger.warning("screen: failed on %s", ticker, exc_info=True)
            continue  # one bad ticker must not lose the rest of the digest
        if described is not None:
            rows.append(ScreenRow(**described))
    return ScreenResponse(session_date=session_date, rows=rows)


@router.get("/nominate", response_model=NominateResponse)
def nominate() -> NominateResponse:
    engine = _engine()
    store.ensure_table(engine)
    session_date = get_effective_trading_date("us").strftime("%Y-%m-%d")

    # Persistence is the daily cache: if today is already screened, serve it.
    # `history` is captured so past rows can be graded off the same batch download.
    history: Dict[str, object] = {}
    existing = store.list_for_date(engine, session_date)
    if not existing:
        history = download_history(NDX_100)
        noms: List[dict] = []
        for ticker, df in history.items():
            noms.extend(screen_one(_trim_to_session(df, session_date), ticker))
        store.persist_nominations(engine, session_date, noms)
        existing = store.list_for_date(engine, session_date)

    store.grade_pending(engine, _price_lookup_factory(history))

    prev_by_rule = {r: store.tickers_for_date(engine, _prev_session(engine, session_date), r)
                    for r in _RULES}

    groups: Dict[str, List[Candidate]] = {r: [] for r in _RULES}
    for row in existing:
        rule = row["rule"]
        groups.setdefault(rule, []).append(Candidate(
            is_new=row["ticker"] not in prev_by_rule.get(rule, set()),
            **{k: row.get(k) for k in ("ticker", "rule", "trend_status", "trend_strength",
               "signal_score", "vol_ratio", "off_20d_high_pct", "rsi6", "entry_close")}))
    for r in groups:
        groups[r].sort(key=lambda c: (-(c.trend_strength or 0), -(c.signal_score or 0)))
    return NominateResponse(session_date=session_date, groups=groups)


def _latest_close(ticker: str):
    import time
    import yfinance as yf
    for _ in range(2):  # yfinance single-ticker calls are flaky after a batch; retry once
        try:
            df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
            if len(df):
                return float(df["Close"].dropna().iloc[-1])
        except Exception:
            pass
        time.sleep(0.4)
    return None


def _graded_return(row):
    """The stored forward outcome (no live fetch) — prefer 20d, else 5d."""
    if row.get("ret_20d") is not None:
        return row["ret_20d"] * 100, "20d"
    if row.get("ret_5d") is not None:
        return row["ret_5d"] * 100, "5d"
    return None, None


@router.get("/history", response_model=HistoryResponse)
def history(ticker: str = Query(...), limit: int = Query(10, ge=1, le=50)) -> HistoryResponse:
    engine = _engine()
    store.ensure_table(engine)
    rows = store.list_for_ticker(engine, ticker, limit)
    # Live price only needed for not-yet-graded rows; fetch once, best-effort.
    need_live = any(_graded_return(r)[0] is None for r in rows)
    latest = _latest_close(ticker) if (rows and need_live) else None
    calls = []
    for row in rows:
        entry = row.get("entry_close")
        gret, horizon = _graded_return(row)
        if gret is not None:  # graded outcome — the real, stored forward return
            calls.append(HistoryItem(session_date=row["session_date"], rule=row["rule"],
                         entry_close=entry, latest_close=None, return_pct=gret, horizon=horizon))
        elif latest and entry:  # not graded yet — live since-entry return
            calls.append(HistoryItem(session_date=row["session_date"], rule=row["rule"],
                         entry_close=entry, latest_close=latest,
                         return_pct=(latest / entry - 1.0) * 100, horizon="live"))
        else:  # too young + no price — pending, entry only (never "$None")
            calls.append(HistoryItem(session_date=row["session_date"], rule=row["rule"],
                         entry_close=entry, latest_close=None, return_pct=None, horizon=None))
    return HistoryResponse(ticker=ticker.upper(), calls=calls)


@router.get("/track-record", response_model=TrackRecordResponse)
def track_record() -> TrackRecordResponse:
    engine = _engine()
    store.ensure_table(engine)
    rows = store._rows(engine, "SELECT rule, ret_20d FROM signal_nominations "
                       "WHERE ret_20d IS NOT NULL", {})
    by_rule: Dict[str, List[float]] = {}
    for r in rows:
        by_rule.setdefault(r["rule"], []).append(r["ret_20d"])
    out = [TrackRecordRule(rule=rule, n=len(v),
           mean_20d_pct=(sum(v) / len(v) * 100) if v else None) for rule, v in by_rule.items()]
    return TrackRecordResponse(rules=out)
