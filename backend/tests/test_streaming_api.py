import json
import unittest
from unittest.mock import AsyncMock, patch

from app.api.routes.tasks import stream_task
from app.schemas.tasks import TaskRequest


class StreamingAPITests(unittest.IsolatedAsyncioTestCase):

    async def test_stream_sends_activity_result_and_completion(self):

        async def mocked_stream(*args, **kwargs):
            yield "custom", {
                "agent": "Research Agent",
                "status": "running",
            }

            yield "values", {
                "status": "completed",
                "workflow": "multi_agent",
                "selected_agent": "Research Agent → Deep Analysis Agent",
                "response": "The final research and analysis report.",
                "video_url": None,
                "video_filename": None,
                "tool_events": [],
                "activity_events": [
                    {"agent": "Research Agent", "status": "completed"}
                ],
            }

        with (
            patch("app.api.routes.tasks.ensure_ai_configured"),
            patch(
                "app.api.routes.tasks.agent_graph.astream",
                new=mocked_stream,
            ),
            patch(
                "app.api.routes.tasks.save_task",
                new=AsyncMock(return_value="test-task-123"),
            ) as save_task,
        ):
            response = await stream_task(
                TaskRequest(request="Research renewable energy.")
            )

            chunks = [
                chunk async for chunk in response.body_iterator
            ]

        parsed_events = []

        for chunk in chunks:
            lines = chunk.splitlines()
            event_name = next(
                line.removeprefix("event: ").strip()
                for line in lines
                if line.startswith("event: ")
            )
            data_line = next(
                line.removeprefix("data: ")
                for line in lines
                if line.startswith("data: ")
            )
            parsed_events.append(
                (event_name, json.loads(data_line))
            )

        event_names = [
            event_name for event_name, _ in parsed_events
        ]

        self.assertEqual(
            event_names,
            ["status", "activity", "result", "status"],
        )

        self.assertEqual(
            parsed_events[0][1]["status"],
            "started",
        )

        self.assertEqual(
            parsed_events[1][1]["agent"],
            "Research Agent",
        )

        result_data = parsed_events[2][1]

        self.assertEqual(result_data["status"], "completed")
        self.assertEqual(
            result_data["response"],
            "The final research and analysis report.",
        )
        self.assertEqual(
            result_data["task_id"],
            "test-task-123",
        )

        self.assertEqual(
            parsed_events[3][1]["status"],
            "completed",
        )

        save_task.assert_awaited_once()
        self.assertEqual(save_task.await_args.kwargs["status"], "completed")

        print("INITIAL STATUS EVENT: PASS")
        print("ACTIVITY EVENT: PASS")
        print("FINAL RESULT EVENT: PASS")
        print("COMPLETION STATUS EVENT: PASS")
        print("COMPLETED TASK SAVING: PASS")

    async def test_stream_sends_error_and_saves_failed_task(self):

        async def failing_stream(*args, **kwargs):
            raise RuntimeError("Simulated workflow failure")
            yield

        with (
            patch("app.api.routes.tasks.ensure_ai_configured"),
            patch(
                "app.api.routes.tasks.agent_graph.astream",
                new=failing_stream,
            ),
            patch(
                "app.api.routes.tasks.save_task",
                new=AsyncMock(),
            ) as save_task,
        ):
            with self.assertLogs(
                "app.api.routes.tasks",
                level="ERROR",
            ):
                response = await stream_task(
                    TaskRequest(request="Test a failed stream.")
                )

                chunks = [
                    chunk async for chunk in response.body_iterator
                ]

        self.assertEqual(len(chunks), 2)
        self.assertIn("event: status", chunks[0])
        self.assertIn("event: error", chunks[1])
        self.assertIn('"status": "failed"', chunks[1])

        save_task.assert_awaited_once_with(
            "Test a failed stream.",
            {"response": "Task execution failed."},
            status="failed",
        )

        print("STREAM ERROR EVENT: PASS")
        print("FAILED TASK HISTORY: PASS")


if __name__ == "__main__":
    unittest.main()
