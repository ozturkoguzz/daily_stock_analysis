# -*- coding: utf-8 -*-
"""Fill phase_decision fields we already know, instead of asking the model twice.

Production logs show 131 agent analyses failing the integrity check, 116 of them
missing exactly:

    phase_context · watch_conditions · data_limitations

The agent path does not retry (pipeline.py: "placeholder fill only, no LLM
retry"), so those reports ship saying "Model did not provide ...".

Two of the three never needed the model at all:

* `phase_context` must be a dict -- and build_market_phase_context() already
  produced exactly that dict earlier in the same run.
* `data_limitations` must be a list -- and what the run could not see (stale
  bar, forming bar, no news retrieved) is known from run state. Stating it from
  facts is more trustworthy than having the model recall it.

`watch_conditions` is genuine model judgment and is deliberately left alone.
"""

import unittest

from src.services.phase_decision_fill import fill_known_phase_decision_fields


class _Result:
    """Minimal stand-in exposing the dashboard dict the real result carries."""

    def __init__(self, dashboard=None):
        self.dashboard = dashboard if dashboard is not None else {}


def _phase(**kw):
    base = {
        "market": "us",
        "phase": "premarket",
        "session_date": "2026-07-27",
        "effective_daily_bar_date": "2026-07-24",
        "is_trading_day": True,
        "is_partial_bar": False,
    }
    base.update(kw)
    return base


class TestPhaseContextFill(unittest.TestCase):
    def test_phase_context_is_taken_from_the_context_we_already_built(self) -> None:
        result = _Result()
        phase = _phase()
        filled = fill_known_phase_decision_fields(result, phase, has_news=True)

        got = result.dashboard["phase_decision"]["phase_context"]
        self.assertIsInstance(got, dict)
        self.assertEqual(got["effective_daily_bar_date"], "2026-07-24")
        self.assertEqual(got["phase"], "premarket")
        self.assertIn("dashboard.phase_decision.phase_context", filled)

    def test_an_existing_phase_context_is_never_overwritten(self) -> None:
        result = _Result({"phase_decision": {"phase_context": {"phase": "model_supplied"}}})
        filled = fill_known_phase_decision_fields(result, _phase(), has_news=True)

        self.assertEqual(
            result.dashboard["phase_decision"]["phase_context"]["phase"], "model_supplied")
        self.assertNotIn("dashboard.phase_decision.phase_context", filled)

    def test_nothing_is_filled_without_a_phase_context(self) -> None:
        result = _Result()
        self.assertEqual(fill_known_phase_decision_fields(result, None, has_news=True), [])
        self.assertEqual(result.dashboard, {})


class TestDataLimitationsFill(unittest.TestCase):
    def _limits(self, phase, has_news=True):
        result = _Result()
        fill_known_phase_decision_fields(result, phase, has_news=has_news)
        return result.dashboard["phase_decision"]["data_limitations"]

    def test_a_stale_bar_is_stated_with_its_date(self) -> None:
        limits = self._limits(_phase(session_date="2026-07-27",
                                     effective_daily_bar_date="2026-07-24"))
        self.assertTrue(any("2026-07-24" in x for x in limits), limits)

    def test_a_forming_bar_is_stated(self) -> None:
        limits = self._limits(_phase(is_partial_bar=True, phase="intraday",
                                     effective_daily_bar_date="2026-07-27"))
        self.assertTrue(any("not yet closed" in x.lower() or "forming" in x.lower()
                            for x in limits), limits)

    def test_missing_news_is_stated(self) -> None:
        limits = self._limits(_phase(), has_news=False)
        self.assertTrue(any("news" in x.lower() for x in limits), limits)

    def test_a_clean_complete_session_claims_no_false_limitation(self) -> None:
        limits = self._limits(
            _phase(phase="postmarket", session_date="2026-07-24",
                   effective_daily_bar_date="2026-07-24", is_partial_bar=False),
            has_news=True)
        # Must stay a list (the integrity check requires list), but must not
        # invent limitations that do not exist.
        self.assertIsInstance(limits, list)
        self.assertFalse(any("2026-07-24 session close" in x for x in limits), limits)

    def test_existing_data_limitations_are_not_replaced(self) -> None:
        result = _Result({"phase_decision": {"data_limitations": ["model said something"]}})
        fill_known_phase_decision_fields(result, _phase(), has_news=False)
        self.assertEqual(
            result.dashboard["phase_decision"]["data_limitations"], ["model said something"])


class TestWatchConditionsUntouched(unittest.TestCase):
    def test_watch_conditions_is_left_to_the_model(self) -> None:
        result = _Result()
        filled = fill_known_phase_decision_fields(result, _phase(), has_news=True)
        self.assertNotIn("dashboard.phase_decision.watch_conditions", filled)
        self.assertNotIn("watch_conditions", result.dashboard["phase_decision"])


if __name__ == "__main__":
    unittest.main()
