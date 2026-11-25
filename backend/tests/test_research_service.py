import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services.research_service import (
    TAVILY_SEARCH_URL,
    _normalize_source,
    _prepare_sources,
    search_web,
)


class ResearchSourceTests(unittest.TestCase):
    def test_deduplicates_urls_and_preserves_metadata(self):
        sources = _prepare_sources([
            {
                "title": "Official report",
                "url": "https://agency.gov/reports/1#summary",
                "content": "The excerpt.",
                "published_date": "2025-01-02",
                "score": 0.91,
            },
            {
                "title": "Duplicate report",
                "url": "https://agency.gov/reports/1",
                "content": "Duplicate.",
            },
        ], 5)

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["id"], 1)
        self.assertEqual(sources[0]["url"], "https://agency.gov/reports/1")
        self.assertEqual(sources[0]["domain"], "agency.gov")
        self.assertEqual(sources[0]["source_type"], "official")
        self.assertEqual(sources[0]["published_date"], "2025-01-02")
        self.assertEqual(sources[0]["relevance"], 0.91)

    def test_rejects_invalid_urls_and_records(self):
        invalid = [
            None,
            {},
            {"title": "No URL", "url": ""},
            {"title": "Unsafe scheme", "url": "javascript:alert(1)"},
            {"title": "Local host", "url": "http://localhost/private"},
            {"title": "Private IP", "url": "http://192.168.1.1/page"},
            {"title": "Malformed URL", "url": "http://[bad"},
        ]
        self.assertTrue(all(_normalize_source(item) is None for item in invalid))

    def test_caps_results_and_ignores_non_list_payload(self):
        self.assertEqual(_prepare_sources({}, 5), [])
        sources = _prepare_sources([
            {"title": f"Source {i}", "url": f"https://example{i}.org"}
            for i in range(7)
        ], 3)
        self.assertEqual(len(sources), 3)

    def test_invalid_relevance_is_not_preserved(self):
        source = _normalize_source({
            "title": "Example",
            "url": "https://example.org",
            "score": float("nan"),
        })
        self.assertIsNone(source["relevance"])

    def test_rejects_unrelated_authoritative_sources_and_ranks_relevant_results(self):
        sources = _prepare_sources([
            {
                "title": "Indiana University Library Research Guide",
                "url": "https://guides.lib.indiana.edu/un-history",
                "content": "Guide to sources about United Nations history.",
                "score": 0.99,
            },
            {
                "title": "UN Charter | United Nations",
                "url": "https://www.un.org/en/about-us/un-charter",
                "content": "The Charter text and its provisions.",
                "score": 0.7,
            },
        ], 5, query="History of the United Nations")

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["url"], "https://www.un.org/en/about-us/un-charter")
        self.assertEqual(sources[0]["source_role"], "primary")
        self.assertEqual(sources[1]["source_role"], "secondary")
        self.assertEqual(sources[1]["source_kind"], "reference_guide")

    def test_duplicate_urls_merge_the_better_excerpt_without_double_counting(self):
        sources = _prepare_sources([
            {
                "title": "UN Charter",
                "url": "https://www.un.org/charter#top",
                "content": "Short excerpt.",
                "score": 0.4,
            },
            {
                "title": "United Nations Charter",
                "url": "https://www.un.org/charter",
                "content": "A longer excerpt with useful details about the Charter.",
                "score": 0.9,
                "published_date": "2025-01-01",
            },
        ], 6, query="United Nations Charter")

        self.assertEqual(len(sources), 1)
        self.assertIn("useful details", sources[0]["excerpt"])
        self.assertEqual(sources[0]["relevance"], 0.9)
        self.assertEqual(sources[0]["published_date"], "2025-01-01")


class TavilySearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_tavily_is_called_and_returns_primary_and_secondary_metadata(self):
        response = httpx.Response(200, json={"results": [
            {
                "title": "Indiana University Library Research Guide",
                "url": "https://guides.lib.indiana.edu/un-history",
                "content": "A guide to UN history sources.",
                "score": 0.99,
            },
            {
                "title": "UN Charter | United Nations",
                "url": "https://www.un.org/en/about-us/un-charter",
                "content": "Official Charter text.",
                "score": 0.7,
            },
        ]}, request=httpx.Request("POST", TAVILY_SEARCH_URL))
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with (
            patch("app.services.research_service.settings.tavily_api_key", "test-key"),
            patch("app.services.research_service.httpx.AsyncClient", return_value=context),
        ):
            result = await search_web("United Nations Charter")

        client.post.assert_awaited_once()
        payload = client.post.await_args.kwargs["json"]
        self.assertEqual(payload["max_results"], 5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sources_found"], 2)
        self.assertEqual(result["results"][0]["source_role"], "primary")
        self.assertEqual(result["results"][1]["source_kind"], "reference_guide")
        self.assertEqual(result["results"][0]["title"], "UN Charter | United Nations")

    async def test_empty_results_are_reported_as_successful_empty_search(self):
        response = httpx.Response(
            200,
            json={"results": []},
            request=httpx.Request("POST", TAVILY_SEARCH_URL),
        )
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with (
            patch("app.services.research_service.settings.tavily_api_key", "test-key"),
            patch("app.services.research_service.httpx.AsyncClient", return_value=context),
        ):
            result = await search_web("No matching records")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sources_found"], 0)

    async def test_tavily_http_failure_is_logged_and_returned(self):
        response = httpx.Response(
            401,
            request=httpx.Request("POST", TAVILY_SEARCH_URL),
        )
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with (
            patch("app.services.research_service.settings.tavily_api_key", "test-key"),
            patch("app.services.research_service.httpx.AsyncClient", return_value=context),
            self.assertLogs("app.services.research_service", level="WARNING"),
        ):
            result = await search_web("United Nations Charter")

        self.assertEqual(result["status"], "error")
        self.assertIn("rejected", result["reason"])

    async def test_missing_api_key_does_not_call_tavily(self):
        with (
            patch("app.services.research_service.settings.tavily_api_key", ""),
            patch("app.services.research_service.httpx.AsyncClient") as client,
        ):
            result = await search_web("United Nations Charter")

        client.assert_not_called()
        self.assertEqual(result["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
