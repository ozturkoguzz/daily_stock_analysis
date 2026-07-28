"""Persist /signals nominations at fire-time (forward returns cannot be backfilled) and
read them back. Idempotent per (session_date, ticker, rule)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Set

from sqlalchemy import text


def ensure_table(engine) -> None:
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS signal_nominations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                rule TEXT NOT NULL,
                trend_status TEXT, trend_strength INTEGER, signal_score INTEGER,
                vol_ratio REAL, off_20d_high_pct REAL, rsi6 REAL, entry_close REAL,
                ret_5d REAL, ret_20d REAL, graded_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (session_date, ticker, rule)
            )
        """))
        # A screened session that nominated nothing writes no nomination rows,
        # which made "we scanned and found nothing" indistinguishable from "we
        # never scanned". The board is empty ~43% of sessions, so that was half
        # the history unprovable. This marker records the screen itself.
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS signal_scan_sessions (
                session_date TEXT PRIMARY KEY,
                screened_at TEXT NOT NULL,
                universe_size INTEGER NOT NULL,
                nomination_count INTEGER NOT NULL
            )
        """))


def mark_session_screened(engine, session_date: str, universe_size: int,
                          nomination_count: int) -> None:
    """Record that the screen ran for this session, nominations or not."""
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO signal_scan_sessions
                (session_date, screened_at, universe_size, nomination_count)
            VALUES (:d, :at, :u, :n)
            ON CONFLICT(session_date) DO UPDATE SET
                screened_at=excluded.screened_at,
                universe_size=excluded.universe_size,
                nomination_count=excluded.nomination_count
        """), {"d": session_date, "at": datetime.now(timezone.utc).isoformat(),
               "u": universe_size, "n": nomination_count})


def get_session(engine, session_date: str) -> Optional[Dict]:
    rows = _rows(engine, "SELECT session_date, screened_at, universe_size, "
                 "nomination_count FROM signal_scan_sessions WHERE session_date=:d",
                 {"d": session_date})
    return rows[0] if rows else None


def session_screened(engine, session_date: str) -> bool:
    """Whether the screen already ran today -- the real daily-cache key.

    Keying the cache on "are there nomination rows" meant an empty session
    re-downloaded the whole universe on every /signals call.
    """
    return get_session(engine, session_date) is not None


def persist_nominations(engine, session_date: str, noms: List[Dict]) -> int:
    if not noms:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with engine.begin() as c:
        for n in noms:
            res = c.execute(text("""
                INSERT OR IGNORE INTO signal_nominations
                (session_date, ticker, rule, trend_status, trend_strength, signal_score,
                 vol_ratio, off_20d_high_pct, rsi6, entry_close, created_at)
                VALUES (:session_date, :ticker, :rule, :trend_status, :trend_strength,
                 :signal_score, :vol_ratio, :off_20d_high_pct, :rsi6, :entry_close, :created_at)
            """), {"session_date": session_date, "created_at": now, **{
                k: n.get(k) for k in ("ticker", "rule", "trend_status", "trend_strength",
                "signal_score", "vol_ratio", "off_20d_high_pct", "rsi6", "entry_close")}})
            inserted += int(res.rowcount or 0)
    return inserted


def _rows(engine, sql: str, params: Dict) -> List[Dict]:
    with engine.begin() as c:
        return [dict(m) for m in c.execute(text(sql), params).mappings().all()]


def list_for_date(engine, session_date: str) -> List[Dict]:
    return _rows(engine, "SELECT * FROM signal_nominations WHERE session_date=:d "
                 "ORDER BY rule, trend_strength DESC, signal_score DESC", {"d": session_date})


def list_for_ticker(engine, ticker: str, limit: int = 20) -> List[Dict]:
    return _rows(engine, "SELECT * FROM signal_nominations WHERE ticker=:t "
                 "ORDER BY session_date DESC LIMIT :n", {"t": ticker.upper(), "n": limit})


def tickers_for_date(engine, session_date: str, rule: str) -> Set[str]:
    return {r["ticker"] for r in _rows(engine,
            "SELECT ticker FROM signal_nominations WHERE session_date=:d AND rule=:r",
            {"d": session_date, "r": rule})}


def grade_pending(engine, price_lookup: Callable[[str, str, int], Optional[float]]) -> int:
    pending = _rows(engine, "SELECT id, ticker, session_date, entry_close FROM "
                    "signal_nominations WHERE ret_20d IS NULL OR ret_5d IS NULL", {})
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    with engine.begin() as c:
        for row in pending:
            entry = row["entry_close"]
            if not entry:
                continue
            fields = {}
            for horizon, col in ((5, "ret_5d"), (20, "ret_20d")):
                px = price_lookup(row["ticker"], row["session_date"], horizon)
                if px is not None:
                    fields[col] = px / entry - 1.0
            if fields:
                sets = ", ".join(f"{k}=:{k}" for k in fields)
                c.execute(text(f"UPDATE signal_nominations SET {sets}, graded_at=:g WHERE id=:id"),
                          {**fields, "g": now, "id": row["id"]})
                updated += 1
    return updated
