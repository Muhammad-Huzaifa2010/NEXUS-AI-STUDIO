import asyncio
import unittest

from app.workflows.workflow_utils import (
    advance_workflow,
    build_agent_context,
    route_after_agent,
    save_agent_output,
    select_agent,
)


class WorkflowRoutingTests(unittest.TestCase):
    def test_orchestrator_starts_with_first_planned_agent(self):
        state = {"task_plan": ["research", "content"], "current_step": 0}
        self.assertEqual(select_agent(state), "research")

    def test_invalid_first_agent_falls_back_to_content(self):
        state = {"task_plan": ["unknown"], "current_step": 0}
        self.assertEqual(select_agent(state), "content")

    def test_empty_plan_falls_back_to_content(self):
        self.assertEqual(select_agent({"task_plan": []}), "content")

    def test_advance_increments_current_step(self):
        result = asyncio.run(advance_workflow({"current_step": 0}))
        self.assertEqual(result["current_step"], 1)

    def test_routes_to_second_agent_after_first_finishes(self):
        state = {"task_plan": ["research", "content"], "current_step": 1}
        self.assertEqual(route_after_agent(state), "content")

    def test_routes_to_finalize_after_last_agent(self):
        state = {"task_plan": ["research", "content"], "current_step": 2}
        self.assertEqual(route_after_agent(state), "finalize")

    def test_single_agent_plan_finishes_after_first_agent(self):
        state = {"task_plan": ["execution"], "current_step": 1}
        self.assertEqual(route_after_agent(state), "finalize")

    def test_unknown_next_agent_routes_to_finalize(self):
        state = {"task_plan": ["research", "unknown"], "current_step": 1}
        self.assertEqual(route_after_agent(state), "finalize")

    def test_agent_context_contains_previous_specialist_output(self):
        state = {
            "request": "Research renewable energy and write a summary.",
            "agent_outputs": {"research": "Solar and wind are renewable sources."},
        }
        context = build_agent_context(state)
        self.assertIn(state["request"], context)
        self.assertIn("Solar and wind are renewable sources.", context)
        self.assertIn("Previous specialist outputs", context)

    def test_save_agent_output_preserves_prior_results(self):
        state = {"agent_outputs": {"research": "Research result"}}
        updated = save_agent_output(state, "content", "Content result")
        self.assertEqual(updated["research"], "Research result")
        self.assertEqual(updated["content"], "Content result")
        self.assertNotIn("content", state["agent_outputs"])


if __name__ == "__main__":
    unittest.main()
