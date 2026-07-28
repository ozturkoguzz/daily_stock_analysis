# -*- coding: utf-8 -*-
"""Analyst-rating and earnings intel, pre-fetched rather than tool-called.

No skill declares search_comprehensive_intel, so analyst ratings and earnings
were structurally unreachable in production: the agent chose search_stock_news
460 times against 146 intel calls, and none of the shipped US skills name the
intel tool at all.

Declaring the tool was rejected -- 28 runs already log "Agent hit max steps",
so a tool call costs a scarce step and still only *might* fire. This pre-fetches
once, before the agent starts, and hands the result over via news_context.

Design validated against the live API before coding:

* ONE compound query at max_results=20 returned 17 analyst / 16 earnings hits
  with zero noise, beating three focused queries (10 / 9) at a third of the
  cost -- max_results is free, only search_depth bills.
* `basic` depth was identical on MRVL but returned 10 results instead of 20 on
  OSCR and 17 on RKLB, so `advanced` is kept.
* `days` is silently ignored unless topic="news", and 0/20 results carried a
  published date. These are undated reference pages, so the freshness filter
  must never touch them.
* Routing this through search_stock_news (which does filter) returned Nvidia,
  Apple and Modine for an MRVL query. That path is unusable here.
"""

import sys
import unittest
from unittest.mock import MagicMock

if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.search_service import SearchResponse, SearchResult, SearchService


def _svc(provider=None):
    service = SearchService(
        searxng_public_instances_enabled=False,
        news_max_age_days=3,
        news_strategy_profile="short",
    )
    service._providers = [provider] if provider is not None else []
    return service


def _provider(results, calls=None, name="Tavily", fail=False):
    from src.search_service import TavilySearchProvider

    provider = TavilySearchProvider(["dummy"])

    def search(query, max_results=5, days=7, **kwargs):
        if calls is not None:
            calls.append({"query": query, "max_results": max_results,
                          "days": days, **kwargs})
        if fail:
            return SearchResponse(query=query, results=[], provider=name,
                                  success=False, error_message="boom")
        return SearchResponse(query=query, results=list(results),
                              provider=name, success=True)

    provider.search = search
    return provider


def _r(title, url, snippet="Analyst price target raised to 253.69 average.", **kw):
    return SearchResult(title=title, snippet=snippet, url=url,
                        source=kw.get("source", "example.com"),
                        published_date=kw.get("published_date"))


class TestSearchAnalystIntel(unittest.TestCase):
    def setUp(self) -> None:
        SearchService.clear_cache()

    tearDown = setUp

    def test_one_call_with_the_validated_parameters(self) -> None:
        calls = []
        svc = _svc(_provider([_r("MRVL price target", "https://e.com/1")], calls))
        svc.search_analyst_intel("MRVL", "Marvell Technology")

        self.assertEqual(len(calls), 1, "must be a single compound query")
        call = calls[0]
        self.assertEqual(call["max_results"], 20, "max_results is free; take the width")
        self.assertIsNone(call.get("topic"), "topic=news would re-enable date filtering")
        self.assertIn("analyst", call["query"].lower())
        self.assertIn("earnings", call["query"].lower())
        self.assertIn("MRVL", call["query"])

    def test_undated_results_survive(self) -> None:
        # Every real result came back with published_date=None. Dropping them
        # would discard the entire feature.
        svc = _svc(_provider([
            _r("MRVL Analyst Estimates & Ratings", "https://e.com/1"),
            _r("MRVL Price Targets", "https://e.com/2"),
        ]))
        out = svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertEqual(len(out.results), 2)

    def test_repeat_is_served_from_cache(self) -> None:
        calls = []
        svc = _svc(_provider([_r("MRVL price target", "https://e.com/1")], calls))
        svc.search_analyst_intel("MRVL", "Marvell Technology")
        svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertEqual(len(calls), 1, "second analysis must not re-buy")

    def test_duplicate_urls_are_collapsed(self) -> None:
        svc = _svc(_provider([
            _r("A", "https://e.com/same"),
            _r("B", "https://e.com/same"),
            _r("C", "https://e.com/other"),
        ]))
        out = svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertEqual([x.url for x in out.results],
                         ["https://e.com/same", "https://e.com/other"])

    def test_result_count_is_capped(self) -> None:
        svc = _svc(_provider([_r(f"T{i}", f"https://e.com/{i}") for i in range(20)]))
        out = svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertLessEqual(len(out.results), 6)

    def test_scraped_table_snippets_are_dropped_but_titles_kept(self) -> None:
        # Real case: the WSJ result's snippet was a historical price table.
        table = "### Historical Prices | 07/23/26 | 207.86 | 214.56 | 205.02 | 16.36 M |"
        svc = _svc(_provider([_r("MRVL Analyst Estimates", "https://e.com/1", table)]))
        out = svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertEqual(len(out.results), 1)
        self.assertIn("Analyst Estimates", out.results[0].title)
        self.assertEqual(out.results[0].snippet, "")

    def test_snippets_are_truncated(self) -> None:
        svc = _svc(_provider([_r("MRVL", "https://e.com/1", "word " * 200)]))
        out = svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertLessEqual(len(out.results[0].snippet), 200)

    def test_provider_failure_is_soft(self) -> None:
        svc = _svc(_provider([], fail=True))
        out = svc.search_analyst_intel("MRVL", "Marvell Technology")
        self.assertEqual(out.results, [])

    def test_no_provider_is_soft(self) -> None:
        out = _svc().search_analyst_intel("MRVL", "Marvell Technology")
        self.assertEqual(out.results, [])


class TestFormatting(unittest.TestCase):
    def test_block_is_labelled_and_does_not_claim_freshness(self) -> None:
        from src.search_service import format_analyst_intel_block

        text = format_analyst_intel_block(
            SearchResponse(query="q", provider="Tavily", success=True, results=[
                _r("MRVL Price Targets", "https://e.com/1",
                   "Low 110.00 Average 253.69 High 400.00"),
            ]),
            "Marvell Technology",
        )
        self.assertIn("Marvell Technology", text)
        self.assertIn("253.69", text)
        lowered = text.lower()
        self.assertIn("undated", lowered)
        self.assertNotIn("latest news", lowered)

    def test_empty_response_yields_no_block(self) -> None:
        from src.search_service import format_analyst_intel_block

        empty = SearchResponse(query="q", provider="Tavily", success=True, results=[])
        self.assertEqual(format_analyst_intel_block(empty, "Marvell"), "")


if __name__ == "__main__":
    unittest.main()
