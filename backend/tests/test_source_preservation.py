import unittest
from unittest.mock import AsyncMock, patch

from app.workflows.agent_graph import deep_analysis_agent, deliver_response


class ResearchSourceDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_response_lists_only_retrieved_sources(self):
        response = await deliver_response({
            "task_plan": ["research"],
            "response": (
                "## Findings\n\n"
                "See [a fabricated page](https://fake.example/claim).\n\n"
                "## Sources\n\nInvented source list."
            ),
            "research_sources": [
                {
                    "id": 1,
                    "title": "Official report",
                    "url": "https://example.org/report?section=1",
                    "domain": "example.org",
                    "published_date": "2025-01-01",
                    "source_type": "official",
                },
                {
                    "id": 2,
                    "title": "Research summary",
                    "url": "https://research.example.org/summary",
                    "domain": "research.example.org",
                },
            ],
        })

        self.assertIn("## Sources", response["response"])
        self.assertIn("https://example.org/report?section=1", response["response"])
        self.assertIn("https://research.example.org/summary", response["response"])
        self.assertNotIn("https://fake.example/claim", response["response"])
        self.assertNotIn("Invented source list", response["response"])

    async def test_analysis_discards_model_generated_source_list(self):
        state = {
            "request": "Analyze this topic.",
            "research_sources": [{
                "id": 1,
                "title": "Retrieved report",
                "url": "https://example.org/report",
            }],
            "activity_events": [],
        }

        with (
            patch(
                "app.workflows.agent_graph.ask_model",
                new_callable=AsyncMock,
                return_value=(
                    "# Analysis\n\nThe topic has several implications.\n\n"
                    "## Sources\n\nInvented source\nhttps://fake.example"
                ),
            ),
            patch("app.workflows.agent_graph.publish_stream_event"),
        ):
            result = await deep_analysis_agent(state)

        self.assertIn("The topic has several implications.", result["response"])
        self.assertNotIn("## Sources", result["response"])
        self.assertNotIn("fake.example", result["response"])

    async def test_empty_research_results_add_a_limitation(self):
        result = await deliver_response({
            "task_plan": ["research"],
            "response": "A research summary.",
            "research_sources": [],
            "research_limitations": [],
        })

        self.assertIn("## Research limitations", result["response"])
        self.assertIn("no relevant sources", result["response"])


if __name__ == "__main__":
    unittest.main()
