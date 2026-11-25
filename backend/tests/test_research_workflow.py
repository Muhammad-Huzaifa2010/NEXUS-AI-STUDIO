import unittest
from unittest.mock import AsyncMock, patch

from app.workflows.agent_graph import build_research_queries, research_agent


class ResearchWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_un_history_searches_cover_distinct_evidence_topics(self):
        searches = build_research_queries(
            "Research the historical development of the United Nations.",
            budget=5,
        )

        self.assertEqual(len(searches), 5)
        self.assertEqual({category for category, _ in searches}, {
            "official_history",
            "charter_signing",
            "charter_entry_into_force",
            "first_general_assembly",
            "membership_and_documents",
        })
        self.assertEqual(len({query for _, query in searches}), 5)

    async def test_search_failure_does_not_stop_bounded_search_plan(self):
        empty_success = {"status": "success", "results": []}
        with (
            patch(
                "app.workflows.agent_graph.search_web",
                new_callable=AsyncMock,
                side_effect=[
                    RuntimeError("temporary failure"),
                    empty_success,
                    empty_success,
                    empty_success,
                    empty_success,
                ],
            ) as mock_search,
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
                return_value="No external evidence was returned.",
            ),
            patch("app.workflows.agent_graph.publish_stream_event"),
            self.assertLogs("app.workflows.agent_graph", level="ERROR"),
        ):
            result = await research_agent({
                "request": "Research the history of the United Nations.",
                "activity_events": [],
                "agent_outputs": {},
            })

        self.assertEqual(mock_search.await_count, 5)
        self.assertEqual(result["research_sources"], [])
        self.assertTrue(any(
            "official_history search" in item
            for item in result["research_limitations"]
        ))


if __name__ == "__main__":
    unittest.main()
