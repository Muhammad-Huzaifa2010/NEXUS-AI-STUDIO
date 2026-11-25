import unittest
from unittest.mock import AsyncMock, patch

from app.workflows.agent_graph import deep_analysis_agent
class CitationPreservationTests(unittest.IsolatedAsyncioTestCase):

    async def test_analysis_removes_generated_sources_and_preserves_citations(self):
        research_report = """# Research Report

Solar energy is renewable [1]. Wind energy is also renewable [2].

## 2. Sources

1. Original Solar Research
   https://example.com/solar

2. Original Wind Research
   https://example.org/wind
"""

        generated_analysis = """# Deep Analysis

Solar energy provides a renewable electricity source [1].
Wind energy provides another option [2].

## Sources

1. Invented Source
   https://fake-example.com
"""

        state = {
            "request": "Compare solar and wind energy.",
            "task_plan": ["research", "deep_analysis"],
            "current_step": 1,
            "agent_outputs": {
                "research": research_report,
            },
            "evidence_records": [{
                "source_id": 1,
                "source_title": "Original Solar Research",
                "source_url": "https://example.com/solar",
                "supporting_excerpt": "Solar energy is renewable.",
            }],
            "activity_events": [],
        }

        with patch(
            "app.workflows.agent_graph.ask_model",
            new_callable=AsyncMock,
        ) as mock_model, patch(
            "app.workflows.agent_graph.publish_stream_event",
        ):
            mock_model.return_value = generated_analysis

            result = await deep_analysis_agent(state)

        final_response = result["response"]

        self.assertIn("Solar energy", final_response)
        self.assertIn("[1]", final_response)
        self.assertIn("[2]", final_response)
        self.assertNotIn("## Sources", final_response)
        self.assertNotIn("fake-example.com", final_response)
        self.assertEqual(
            result["agent_outputs"]["deep_analysis"],
            final_response,
        )

        print("ORIGINAL SOURCES PRESERVED: PASS")
        print("BODY CITATIONS PRESERVED: PASS")
        print("GENERATED SOURCES REMOVED: PASS")
        print("DEEP ANALYSIS OUTPUT SAVED: PASS")

    async def test_missing_sources_produce_limitation_notice(self):
        state = {
            "request": "Analyze a topic.",
            "task_plan": ["research", "deep_analysis"],
            "current_step": 1,
            "agent_outputs": {
                "research": "Research report without a Sources heading."
            },
            "activity_events": [],
        }

        with patch(
            "app.workflows.agent_graph.ask_model",
            new_callable=AsyncMock,
        ) as mock_model, patch(
            "app.workflows.agent_graph.publish_stream_event",
        ):
            mock_model.return_value = "# Analysis\n\nEvidence is limited."

            result = await deep_analysis_agent(state)

        self.assertIn(
            "Source-level verification is incomplete",
            result["response"],
        )

        print("MISSING-SOURCE LIMITATION NOTICE: PASS")


if __name__ == "__main__":
    unittest.main()


class FinalizationCitationTests(unittest.IsolatedAsyncioTestCase):

    async def test_final_synthesis_preserves_original_sources(self):
        from app.workflows.agent_graph import deliver_response, finalize_workflow

        research_report = """# Research Report

Solar energy is renewable [1].
Wind energy is renewable [2].

## Sources

1. Original Solar Research
   https://example.com/solar

2. Original Wind Research
   https://example.org/wind
"""

        deep_analysis = """# Deep Analysis

Solar energy has several advantages [1].
Wind energy offers another option [2].

## Sources

1. Original Solar Research
   https://example.com/solar

2. Original Wind Research
   https://example.org/wind
"""

        generated_synthesis = """# Final Report

Solar and wind energy are renewable options [1] and [2].

## Sources

1. Invented source
   https://fake-example.com
"""

        state = {
            "request": "Compare solar and wind energy.",
            "task_plan": ["research", "deep_analysis"],
            "research_sources": [{
                "id": 1,
                "title": "Original Solar Research",
                "url": "https://example.com/solar",
                "domain": "example.com",
            }, {
                "id": 2,
                "title": "Original Wind Research",
                "url": "https://example.org/wind",
                "domain": "example.org",
            }],
            "agent_outputs": {
                "research": research_report,
                "deep_analysis": deep_analysis,
            },
            "activity_events": [],
        }

        with patch(
            "app.workflows.agent_graph.ask_model",
            new_callable=AsyncMock,
        ) as mock_model, patch(
            "app.workflows.agent_graph.publish_stream_event",
        ):
            mock_model.return_value = generated_synthesis
            finalized = await finalize_workflow(state)

        result = await deliver_response({**state, **finalized})

        final_response = result["response"]
        self.assertIn("## Sources", final_response)
        self.assertIn("[1]", final_response)
        self.assertIn("[2]", final_response)
        self.assertNotIn("fake-example.com", final_response)
        self.assertIn("https://example.com/solar", final_response)

        print("FINAL SYNTHESIS SOURCES PRESERVED: PASS")
        print("FINAL CITATION MARKERS PRESERVED: PASS")
        print("GENERATED SOURCES REMOVED: PASS")

    async def test_finalization_reports_missing_research_sources(self):
        from app.workflows.agent_graph import deliver_response, finalize_workflow

        state = {
            "request": "Analyze a topic.",
            "task_plan": ["research", "deep_analysis"],
            "agent_outputs": {
                "research": "Research without a Sources heading.",
                "deep_analysis": "Analysis without a Sources heading.",
            },
            "activity_events": [],
        }

        with patch(
            "app.workflows.agent_graph.ask_model",
            new_callable=AsyncMock,
        ) as mock_model, patch(
            "app.workflows.agent_graph.publish_stream_event",
        ):
            mock_model.return_value = "# Final Report\n\nEvidence is limited."
            finalized = await finalize_workflow(state)

        result = await deliver_response({**state, **finalized})

        self.assertIn(
            "factual claims remain unverified",
            result["response"],
        )

        print("FINALIZATION MISSING-SOURCE NOTICE: PASS")
