# -*- coding: utf-8 -*-
"""Tests for Tavily credit economics.

Two separate wastes, measured against the live Tavily plan:

A. One analysis fired several near-identical "latest news" searches because
   callers (the Agent tool especially, where the LLM supplies the argument)
   pass different stock_name spellings for the same ticker. The name is part
   of both the query and the cache key, so every spelling was a fresh
   2-credit search.

B. The intel loop round-robins providers, which permanently pinned the
   market_analysis and earnings dimensions to SearXNG. SearXNG fails
   essentially always, so those two dimensions never returned anything.
"""

import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.search_service import (
    SearchResponse,
    SearchResult,
    SearchService,
    TavilySearchProvider,
)


def _service(providers=None) -> SearchService:
    service = SearchService(
        searxng_public_instances_enabled=False,
        news_max_age_days=3,
        news_strategy_profile="short",
    )
    if providers is not None:
        service._providers = providers
    return service


def _fake_provider(name="Tavily", calls=None, success=True):
    """A stand-in provider that records every query it is paid for."""
    provider = MagicMock()
    provider.name = name
    provider.is_available = True

    def search(query, max_results=5, days=7, **kwargs):
        if calls is not None:
            calls.append(query)
        if not success:
            return SearchResponse(query=query, results=[], provider=name,
                                  success=False, error_message="Too Many Requests")
        return _ok(query)

    provider.search.side_effect = search
    return provider


def _ok(query: str) -> SearchResponse:
    """A realistic hit.

    The result has to read as direct company news: the service only caches a
    response once it classifies one, so a generic "Headline" would silently
    exercise the uncached path and prove nothing about credit spend.
    """
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SearchResponse(
        query=query,
        results=[
            SearchResult(
                title=f"{query} — quarterly update",
                snippet=f"{query}: the company reported results today.",
                url="https://example.com/a",
                source="example.com",
                published_date=today,
            )
        ],
        provider="Tavily",
        success=True,
    )


class _CacheIsolated(unittest.TestCase):
    """Search results cache per class now, so tests must not inherit each other's."""

    def setUp(self) -> None:
        SearchService.clear_cache()

    tearDown = setUp


class TestNewsQueryDeduplication(_CacheIsolated):
    """A: the same ticker must not be searched once per name spelling."""

    def _run_two_calls(self, first_name: str, second_name: str):
        calls = []
        service = _service([_fake_provider(calls=calls)])
        service.search_stock_news("MRVL", first_name, max_results=5)
        service.search_stock_news("MRVL", second_name, max_results=5)
        return calls

    def test_suffix_variants_of_the_same_name_hit_the_cache(self) -> None:
        calls = self._run_two_calls("Marvell Technology", "Marvell Technology, Inc.")
        self.assertEqual(len(calls), 1, f"expected 1 paid search, got {calls}")

    def test_llm_supplied_keyword_soup_does_not_buy_a_new_search(self) -> None:
        # The Agent tool lets the model pass whatever it likes as stock_name;
        # "Marvell Technology insider selling earnings" was a real observed value.
        calls = self._run_two_calls(
            "Marvell Technology", "Marvell Technology insider selling earnings")
        self.assertEqual(len(calls), 1, f"expected 1 paid search, got {calls}")

    def test_different_tickers_still_get_their_own_search(self) -> None:
        calls = []
        service = _service([_fake_provider(calls=calls)])
        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)
        service.search_stock_news("MU", "Micron Technology", max_results=5)
        self.assertEqual(len(calls), 2)

    def test_focus_keywords_still_distinguish_market_review_queries(self) -> None:
        # Market review reuses stock_code="market" for several different topics;
        # collapsing those onto one cache entry would break it.
        calls = []
        service = _service([_fake_provider(calls=calls)])
        service.search_stock_news(
            "market", "US market", max_results=3, focus_keywords=["US", "stock", "market"])
        service.search_stock_news(
            "market", "US market", max_results=3, focus_keywords=["S&P", "500", "NASDAQ"])
        self.assertEqual(len(calls), 2)


class TestAnalyticalDimensionRouting(_CacheIsolated):
    """B: analyst-rating and earnings intel must reach a provider that works."""

    def test_analytical_dimensions_are_routed_to_tavily(self) -> None:
        tavily_calls, searxng_calls = [], []
        # A real TavilySearchProvider: routing selects on provider type, so a
        # look-alike mock would pass this test while production still misroutes.
        tavily = TavilySearchProvider(["dummy_key"])
        searxng = _fake_provider("SearXNG", calls=searxng_calls, success=False)
        service = _service([tavily, searxng])

        def record(query, max_results=5, days=7, **kwargs):
            tavily_calls.append(query)
            return _ok(query)

        with patch.object(service, "_is_foreign_stock", return_value=True), \
                patch.object(tavily, "search", side_effect=record):
            service.search_comprehensive_intel(
                "MRVL", "Marvell Technology", max_searches=10)

        paid = " || ".join(tavily_calls)
        self.assertIn("analyst rating target price", paid,
                      "market_analysis must not be pinned to the failing provider")
        self.assertIn("earnings revenue profit growth forecast", paid,
                      "earnings must not be pinned to the failing provider")


if __name__ == "__main__":
    unittest.main()


def _generic(query: str) -> SearchResponse:
    """A successful search that yields no *direct* company news."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SearchResponse(
        query=query,
        results=[
            SearchResult(
                title="Wall Street drifts as traders await inflation data",
                snippet="Broad indexes were little changed in early trading.",
                url="https://example.com/macro",
                source="example.com",
                published_date=today,
            )
        ],
        provider="Tavily",
        success=True,
    )


class TestCachingOfEmptyButSuccessfulSearches(_CacheIsolated):
    """A determinate 'nothing relevant' answer must not be re-bought."""

    def test_a_search_with_no_direct_news_is_not_paid_for_twice(self) -> None:
        calls = []
        provider = _fake_provider("Tavily")
        provider.search.side_effect = lambda q, max_results=5, days=7, **k: (
            calls.append(q) or _generic(q))
        service = _service([provider])

        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)
        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)

        self.assertEqual(len(calls), 1, f"expected 1 paid search, got {calls}")

    def test_a_failed_search_is_still_retried(self) -> None:
        # Failures are transient (quota, rate limit, network). Caching them
        # would stretch a blip into a ten-minute outage.
        calls = []
        provider = _fake_provider("Tavily", success=False)
        original = provider.search.side_effect
        provider.search.side_effect = lambda q, max_results=5, days=7, **k: (
            calls.append(q) or original(q, max_results=max_results, days=days, **k))
        service = _service([provider])

        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)
        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)

        self.assertEqual(len(calls), 2, "a transient failure must not be cached")


class TestCacheIsSharedAcrossServiceInstances(_CacheIsolated):
    """The same query must not be bought once per SearchService object.

    Real case, MRVL on 2026-07-27: one analysis paid Tavily twice for the
    identical query 1.6s apart. The analysis pipeline
    (src/core/pipeline.py) constructs its own SearchService while the Agent
    tools (src/agent/tools/search_tools.py) use the module singleton. Each
    object had a private in-memory cache, so no amount of query normalisation
    could make them share a result.
    """

    def test_two_instances_do_not_each_pay_for_the_same_query(self) -> None:
        calls = []

        def provider_for(service_calls):
            provider = _fake_provider("Tavily")
            provider.search.side_effect = lambda q, max_results=5, days=7, **k: (
                service_calls.append(q) or _ok(q))
            return provider

        pipeline_service = _service([provider_for(calls)])
        agent_service = _service([provider_for(calls)])

        pipeline_service.search_stock_news("MRVL", "Marvell Technology", max_results=5)
        agent_service.search_stock_news("MRVL", "Marvell Technology", max_results=5)

        self.assertEqual(len(calls), 1, f"expected 1 paid search across both, got {calls}")

    def test_clear_cache_lets_a_fresh_run_search_again(self) -> None:
        calls = []
        provider = _fake_provider("Tavily")
        provider.search.side_effect = lambda q, max_results=5, days=7, **k: (
            calls.append(q) or _ok(q))
        service = _service([provider])

        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)
        SearchService.clear_cache()
        service.search_stock_news("MRVL", "Marvell Technology", max_results=5)

        self.assertEqual(len(calls), 2)
