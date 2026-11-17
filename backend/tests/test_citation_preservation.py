import unittest
from unittest.mock import AsyncMock, patch

from app.workflows.agent_graph import deep_analysis_agent
from app.workflows.workflow_utils import extract_sources_section


class CitationPreservationTests(unittest.IsolatedAsyncioTestCase):

    async def test_original_sources_are_preserved_verbatim(self):
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
        original_sources = extract_sources_section(research_report)

        self.assertTrue(original_sources)
        self.assertTrue(final_response.endswith(original_sources))
        self.assertIn("Solar energy", final_response)
        self.assertIn("[1]", final_response)
        self.assertIn("[2]", final_response)
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
        from app.workflows.agent_graph import finalize_workflow

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
            result = await finalize_workflow(state)

        final_response = result["response"]
        expected_sources = extract_sources_section(deep_analysis)

        self.assertTrue(expected_sources)
        self.assertTrue(final_response.endswith(expected_sources))
        self.assertIn("[1]", final_response)
        self.assertIn("[2]", final_response)
        self.assertNotIn("fake-example.com", final_response)

        print("FINAL SYNTHESIS SOURCES PRESERVED: PASS")
        print("FINAL CITATION MARKERS PRESERVED: PASS")
        print("GENERATED SOURCES REMOVED: PASS")

    async def test_finalization_reports_missing_research_sources(self):
        from app.workflows.agent_graph import finalize_workflow

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
            result = await finalize_workflow(state)

        self.assertIn(
            "Source-level verification is incomplete",
            result["response"],
        )

        print("FINALIZATION MISSING-SOURCE NOTICE: PASS")
