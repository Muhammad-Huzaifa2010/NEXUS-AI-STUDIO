import unittest
from unittest.mock import AsyncMock, patch

from app.workflows.agent_graph import agent_graph


class WorkflowIntegrationTests(unittest.IsolatedAsyncioTestCase):

    async def test_research_to_deep_analysis_complete_workflow(self):
        research_output = (
            "Research findings: renewable energy includes solar and wind."
        )

        analysis_output = (
            "Deep analysis: solar and wind have different operating "
            "characteristics and should be compared by context."
        )

        final_output = (
            "Final report: solar and wind are both renewable energy options. "
            "Their suitability depends on the requirements of the project."
        )

        mocked_model_responses = [
            '{"agents": ["research", "deep_analysis"]}',
            research_output,
            analysis_output,
            final_output,
        ]

        mocked_search_results = {
            "status": "success",
            "results": [],
        }

        with patch(
            "app.workflows.agent_graph.ask_model",
            new_callable=AsyncMock,
        ) as mock_model, patch(
            "app.workflows.agent_graph.search_web",
            new_callable=AsyncMock,
        ) as mock_search, patch(
            "app.workflows.agent_graph.publish_stream_event",
        ):
            mock_model.side_effect = mocked_model_responses
            mock_search.return_value = mocked_search_results

            result = await agent_graph.ainvoke({
                "request": (
                    "Research renewable energy and critically analyze "
                    "solar and wind energy."
                )
            })

        # 1. Verify the Orchestrator selected the intended agents.
        self.assertEqual(
            result["task_plan"],
            ["research", "deep_analysis"],
        )

        self.assertEqual(result["workflow"], "multi_agent")

        # 2. Verify Research and Deep Analysis both completed.
        outputs = result["agent_outputs"]

        self.assertIn("research", outputs)
        self.assertIn("deep_analysis", outputs)

        self.assertEqual(outputs["research"], research_output)
        self.assertIn("Deep analysis:", outputs["deep_analysis"])

        # 3. Verify Deep Analysis received the Research output.
        deep_analysis_call = mock_model.await_args_list[2]
        deep_analysis_context = deep_analysis_call.kwargs["user_request"]

        self.assertIn(research_output, deep_analysis_context)

        # 4. Verify Final Review produced the final response.
        self.assertIn("Final report:", result["response"])
        self.assertIn("solar and wind", result["response"])

        # 5. Verify the mocked services were used as expected.
        mock_search.assert_awaited_once()
        self.assertEqual(mock_model.await_count, 4)

        # 6. Verify the workflow recorded activity events.
        self.assertTrue(result.get("activity_events"))

        print("ORCHESTRATOR ROUTING: PASS")
        print("RESEARCH AGENT EXECUTION: PASS")
        print("DEEP ANALYSIS EXECUTION: PASS")
        print("RESEARCH-TO-ANALYSIS STATE TRANSFER: PASS")
        print("FINAL REVIEW: PASS")
        print("ACTIVITY EVENTS: PASS")
        print("COMPLETE WORKFLOW INTEGRATION: PASS")


if __name__ == "__main__":
    unittest.main()
