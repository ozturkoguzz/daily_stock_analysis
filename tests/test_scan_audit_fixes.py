# -*- coding: utf-8 -*-
"""Two /signals defects found by audit.

1. _latest_close() returned None for every ticker. yfinance now returns
   MultiIndex columns even for a single ticker, so df["Close"] is a DataFrame
   and float(...iloc[-1]) raises TypeError -- swallowed by a bare except. The
   live-return fallback was therefore dead and every ungraded nomination
   rendered as "pending" with no number.

2. An empty screen left no record. persist_nominations starts
   `if not noms: return 0`, so a session that legitimately nominated nothing is
   indistinguishable from a session that was never screened -- on a board that
   is empty ~43% of sessions, that is half the history unprovable. It also made
   /scan/nominate re-download all 101 tickers on every call during such a day,
   because the daily cache keys on rows existing.
"""

import unittest
from unittest.mock import patch

import pandas as pd

from api.v1.endpoints.scan import _latest_close
from src.services import signal_nomination_store as store


def _multiindex_frame(ticker="TSLA", closes=(300.0, 305.0, 309.22)):
    """What yfinance actually returns today for a single ticker."""
    idx = pd.date_range("2026-07-23", periods=len(closes), freq="D")
    cols = pd.MultiIndex.from_product(
        [["Close", "High", "Low", "Open", "Volume"], [ticker]])
    data = {
        ("Close", ticker): list(closes),
        ("High", ticker): [c * 1.01 for c in closes],
        ("Low", ticker): [c * 0.99 for c in closes],
        ("Open", ticker): [c * 0.995 for c in closes],
        ("Volume", ticker): [1_000_000] * len(closes),
    }
    return pd.DataFrame(data, index=idx).reindex(columns=cols)


def _flat_frame(closes=(300.0, 305.0, 309.22)):
    """The older single-index shape, still worth supporting."""
    idx = pd.date_range("2026-07-23", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": list(closes)}, index=idx)


class TestLatestClose(unittest.TestCase):
    def test_multiindex_columns_yield_a_float(self) -> None:
        with patch("yfinance.download", return_value=_multiindex_frame()):
            self.assertAlmostEqual(_latest_close("TSLA"), 309.22, places=2)

    def test_flat_columns_still_work(self) -> None:
        with patch("yfinance.download", return_value=_flat_frame()):
            self.assertAlmostEqual(_latest_close("TSLA"), 309.22, places=2)

    def test_empty_frame_returns_none(self) -> None:
        with patch("yfinance.download", return_value=pd.DataFrame()):
            self.assertIsNone(_latest_close("TSLA"))

    def test_download_failure_returns_none(self) -> None:
        with patch("yfinance.download", side_effect=RuntimeError("network")):
            self.assertIsNone(_latest_close("TSLA"))


class TestSessionMarker(unittest.TestCase):
    def setUp(self) -> None:
        from sqlalchemy import create_engine
        self.engine = create_engine("sqlite://")
        store.ensure_table(self.engine)

    def test_a_session_is_unscreened_until_marked(self) -> None:
        self.assertFalse(store.session_screened(self.engine, "2026-07-21"))

    def test_marking_an_empty_screen_makes_it_provable(self) -> None:
        store.mark_session_screened(self.engine, "2026-07-21",
                                    universe_size=101, nomination_count=0)
        self.assertTrue(store.session_screened(self.engine, "2026-07-21"))

    def test_the_marker_records_what_was_screened(self) -> None:
        store.mark_session_screened(self.engine, "2026-07-21",
                                    universe_size=101, nomination_count=0)
        row = store.get_session(self.engine, "2026-07-21")
        self.assertEqual(row["universe_size"], 101)
        self.assertEqual(row["nomination_count"], 0)
        self.assertTrue(row["screened_at"])

    def test_marking_twice_does_not_duplicate(self) -> None:
        store.mark_session_screened(self.engine, "2026-07-21", 101, 0)
        store.mark_session_screened(self.engine, "2026-07-21", 101, 2)
        self.assertTrue(store.session_screened(self.engine, "2026-07-21"))
        self.assertEqual(store.get_session(self.engine, "2026-07-21")["nomination_count"], 2)

    def test_other_sessions_are_unaffected(self) -> None:
        store.mark_session_screened(self.engine, "2026-07-21", 101, 0)
        self.assertFalse(store.session_screened(self.engine, "2026-07-22"))


class TestNominateCachesEmptySessions(unittest.TestCase):
    """An empty session must be screened once, not once per request."""

    def test_second_call_on_an_empty_session_does_not_re_download(self):
        import pandas as pd
        from unittest.mock import MagicMock
        from sqlalchemy import create_engine
        from api.v1.endpoints import scan as scan_mod

        engine = create_engine("sqlite://")
        store.ensure_table(engine)
        calls = []

        def fake_download(tickers):
            calls.append(len(tickers))
            # Flat, boring data: nothing trips either rule.
            idx = pd.date_range("2026-01-01", periods=80, freq="D")
            df = pd.DataFrame({
                "date": idx, "open": [100.0] * 80, "high": [100.0] * 80,
                "low": [100.0] * 80, "close": [100.0] * 80, "volume": [1e6] * 80,
            })
            return {"AAA": df}

        with patch.object(scan_mod, "download_history", side_effect=fake_download), \
                patch.object(scan_mod, "_engine", return_value=engine), \
                patch.object(scan_mod, "NDX_100", ["AAA"]), \
                patch.object(scan_mod.store, "grade_pending", MagicMock(return_value=0)):
            first = scan_mod.nominate()
            second = scan_mod.nominate()

        self.assertEqual(len(calls), 1, "empty session must not re-download per call")
        self.assertEqual(first.groups, second.groups)

    def test_an_empty_session_is_still_recorded(self):
        import pandas as pd
        from unittest.mock import MagicMock
        from sqlalchemy import create_engine
        from api.v1.endpoints import scan as scan_mod

        engine = create_engine("sqlite://")
        store.ensure_table(engine)

        def fake_download(tickers):
            idx = pd.date_range("2026-01-01", periods=80, freq="D")
            return {"AAA": pd.DataFrame({
                "date": idx, "open": [100.0] * 80, "high": [100.0] * 80,
                "low": [100.0] * 80, "close": [100.0] * 80, "volume": [1e6] * 80})}

        with patch.object(scan_mod, "download_history", side_effect=fake_download), \
                patch.object(scan_mod, "_engine", return_value=engine), \
                patch.object(scan_mod, "NDX_100", ["AAA"]), \
                patch.object(scan_mod.store, "grade_pending", MagicMock(return_value=0)):
            result = scan_mod.nominate()

        row = store.get_session(engine, result.session_date)
        self.assertIsNotNone(row, "a zero-nomination screen must still be provable")
        self.assertEqual(row["nomination_count"], 0)
        self.assertEqual(row["universe_size"], 1)


if __name__ == "__main__":
    unittest.main()
