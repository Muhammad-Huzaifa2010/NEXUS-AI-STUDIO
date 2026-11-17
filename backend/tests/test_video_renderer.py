import asyncio
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.video_renderer import WIDTH, HEIGHT, VideoRenderCancelled, _draw_scene, _find_speech_engine, _run_process


class VideoRendererTests(unittest.TestCase):
    def test_prefers_macos_say_when_available(self):
        with patch("app.services.video_renderer.shutil.which", side_effect=lambda name: "/usr/bin/say" if name == "say" else None):
            self.assertEqual(_find_speech_engine(), ("say", "/usr/bin/say"))

    def test_uses_espeak_ng_when_say_is_unavailable(self):
        with patch("app.services.video_renderer.shutil.which", side_effect=lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None):
            self.assertEqual(_find_speech_engine(), ("espeak-ng", "/usr/bin/espeak-ng"))

    def test_reports_missing_speech_engine(self):
        with patch("app.services.video_renderer.shutil.which", return_value=None):
            self.assertEqual(_find_speech_engine(), (None, None))

    def test_scene_renderer_writes_full_hd_png(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scene.png"
            _draw_scene("Test video", "Test heading", "Test scene body", 0, 3, output)
            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual(image.size, (WIDTH, HEIGHT))
                self.assertEqual(image.format, "PNG")


class VideoProcessTests(unittest.TestCase):
    def test_runs_process_successfully(self):
        result = _run_process(
            [sys.executable, "-c", "print('process-ok')"],
            timeout=5,
        )
        self.assertEqual(result.stdout.strip(), "process-ok")
        self.assertEqual(result.returncode, 0)

    def test_rejects_pre_cancelled_process(self):
        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaises(VideoRenderCancelled):
            _run_process(
                [sys.executable, "-c", "print('should-not-run')"],
                timeout=5,
                cancel_event=cancel_event,
            )

    def test_cancellation_stops_running_process(self):
        cancel_event = threading.Event()

        def run():
            return _run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=40,
                cancel_event=cancel_event,
            )

        async def check():
            task = asyncio.create_task(asyncio.to_thread(run))
            await asyncio.sleep(0.3)
            cancel_event.set()

            with self.assertRaises(VideoRenderCancelled):
                await asyncio.wait_for(task, timeout=8)

        asyncio.run(check())

    def test_timeout_stops_process(self):
        started = time.monotonic()

        with self.assertRaises(subprocess.TimeoutExpired):
            _run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=0.3,
            )

        self.assertLess(time.monotonic() - started, 5)

    def test_nonzero_exit_raises_called_process_error(self):
        with self.assertRaises(subprocess.CalledProcessError):
            _run_process(
                [sys.executable, "-c", "raise SystemExit(3)"],
                timeout=5,
            )


if __name__ == "__main__":
    unittest.main()
