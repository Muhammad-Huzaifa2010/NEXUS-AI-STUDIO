import os
import shutil
import subprocess
import tempfile
import threading
import time
import textwrap
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1280
HEIGHT = 720
FPS = 24


class VideoRenderCancelled(Exception):
    """Raised when a video render is cancelled."""


def _run_process(command, *, timeout, cancel_event=None):
    """Run a subprocess while supporting cancellation and a hard timeout."""
    if cancel_event and cancel_event.is_set():
        raise VideoRenderCancelled("Video rendering was cancelled.")

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.monotonic() + timeout

    while True:
        if cancel_event and cancel_event.is_set():
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise VideoRenderCancelled("Video rendering was cancelled.")

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(
                command, timeout, output=stdout, stderr=stderr
            )

        try:
            stdout, stderr = process.communicate(
                timeout=min(0.2, remaining)
            )
            break
        except subprocess.TimeoutExpired:
            continue

    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode,
            command,
            output=stdout,
            stderr=stderr,
        )

    return subprocess.CompletedProcess(
        command, process.returncode, stdout, stderr
    )

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORAGE_DIR = Path(os.getenv("NEXUS_STORAGE_DIR", str(PROJECT_ROOT / "storage")))
VIDEO_DIR = STORAGE_DIR / "videos"


def _font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Neue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                pass

    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def _draw_scene(title: str, heading: str, body: str, index: int, total: int, path: Path):
    image = Image.new("RGB", (WIDTH, HEIGHT), (8, 24, 48))
    gradient = ImageDraw.Draw(image)

    # Draw a smooth navy-to-blue gradient in vertical bands. This avoids
    # millions of Python-level pixel assignments for every generated scene.
    bands = 256
    for band in range(bands):
        x0 = int(WIDTH * band / bands)
        x1 = int(WIDTH * (band + 1) / bands)
        blend = int(18 + 20 * (band / bands))
        blue = 48 + int(35 * band / bands)
        gradient.rectangle((x0, 0, x1, HEIGHT), fill=(8, blend, blue))

    draw = ImageDraw.Draw(image, "RGBA")

    # Decorative shapes.
    draw.ellipse((930, -180, 1450, 340), fill=(20, 180, 210, 35))
    draw.ellipse((1010, 420, 1430, 840), fill=(80, 100, 255, 30))
    draw.rounded_rectangle(
        (64, 54, 1216, 666),
        radius=28,
        outline=(100, 210, 255, 100),
        width=2,
    )

    accent_font = _font(24, bold=True)
    title_font = _font(42, bold=True)
    heading_font = _font(58, bold=True)
    body_font = _font(32)

    draw.text((100, 88), "NEXUS AI STUDIO", font=accent_font, fill=(90, 220, 255, 255))
    draw.text(
        (100, 135),
        title[:90],
        font=title_font,
        fill=(245, 249, 255, 255),
    )

    draw.rounded_rectangle(
        (100, 220, 250, 228),
        radius=4,
        fill=(40, 210, 230, 255),
    )

    draw.text(
        (100, 275),
        heading[:100],
        font=heading_font,
        fill=(255, 255, 255, 255),
    )

    lines = _wrap_text(draw, body[:500], body_font, 990)
    y = 380

    for line in lines[:6]:
        draw.text((105, y), line, font=body_font, fill=(205, 220, 240, 255))
        y += 48

    # Scene progress indicator.
    bar_x = 100
    bar_y = 610
    bar_width = 1080
    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + bar_width, bar_y + 8),
        radius=4,
        fill=(65, 85, 125, 180),
    )
    progress = int(bar_width * (index + 1) / total)
    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + progress, bar_y + 8),
        radius=4,
        fill=(45, 210, 230, 255),
    )

    draw.text(
        (1080, 625),
        f"{index + 1:02d} / {total:02d}",
        font=accent_font,
        fill=(190, 220, 245, 255),
    )

    image.save(path, format="PNG", optimize=True)


def _find_speech_engine():
    """Prefer natural online neural speech, then local speech fallbacks."""
    edge_tts = shutil.which("edge-tts")
    if edge_tts:
        return "edge-tts", edge_tts
    say = shutil.which("say")
    if say:
        return "say", say
    espeak = shutil.which("espeak-ng")
    if espeak:
        return "espeak-ng", espeak
    return None, None


def _audio_duration(
    ffprobe: str,
    audio_path: Path,
    cancel_event=None,
) -> float:
    result = _run_process(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        timeout=30,
        cancel_event=cancel_event,
    )
    return float(result.stdout.strip())


def create_video(
    title: str,
    scenes: list[dict],
    narration: str,
    cancel_event=None,
) -> dict:
    """
    Render a narrated slideshow MP4 from validated scene data.

    Each scene should contain:
      - heading: short scene heading
      - body: short supporting text
      - narration: optional scene narration (used for timing weights)
    """
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    speech_engine, speech_executable = _find_speech_engine()

    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and ffprobe must be installed and available on PATH.")

    if not speech_executable:
        raise RuntimeError("Install macOS Speech ('say') or espeak-ng for narration.")

    if not isinstance(title, str) or not title.strip():
        raise ValueError("A video title is required.")

    if not isinstance(narration, str) or not narration.strip():
        raise ValueError("Narration text is required.")

    word_count = len(narration.split())
    if not 600 <= word_count <= 650:
        raise ValueError(
            f"Five-minute narration must contain 600-650 words; received {word_count}."
        )
    if not isinstance(scenes, list) or not 8 <= len(scenes) <= 10:
        raise ValueError("Provide between 8 and 10 scenes.")

    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("Each scene must be an object.")
        if not isinstance(scene.get("heading"), str) or not scene["heading"].strip():
            raise ValueError("Every scene needs a heading.")
        if not isinstance(scene.get("body"), str):
            raise ValueError("Every scene needs body text.")

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.mp4"
    output_path = VIDEO_DIR / filename

    try:
        with tempfile.TemporaryDirectory(prefix="nexus_video_") as temp_dir:
            work_dir = Path(temp_dir)
            audio_extension = (
                "mp3" if speech_engine == "edge-tts"
                else "aiff" if speech_engine == "say"
                else "wav"
            )
            audio_path = work_dir / f"narration.{audio_extension}"
            narration_path = work_dir / "narration.txt"
            concat_path = work_dir / "scenes.txt"
            narration_path.write_text(narration.strip(), encoding="utf-8")

            if speech_engine == "edge-tts":
                voice = os.getenv("NEXUS_TTS_VOICE", "en-US-AriaNeural")
                speech_command = [
                    speech_executable,
                    "--voice", voice,
                    "--rate=-5%",
                    "--file", str(narration_path),
                    "--write-media", str(audio_path),
                ]
            elif speech_engine == "say":
                speech_command = [
                    speech_executable, "-o", str(audio_path),
                    "-f", str(narration_path),
                ]
            else:
                speech_command = [
                    speech_executable, "-f", str(narration_path),
                    "-w", str(audio_path),
                ]

            _run_process(
                speech_command,
                timeout=240,
                cancel_event=cancel_event,
            )
            audio_seconds = _audio_duration(
                ffprobe, audio_path, cancel_event
            )
            if not 270 <= audio_seconds <= 330:
                raise ValueError(
                    f"Narration audio must be 4:30-5:30; generated {audio_seconds:.1f} seconds."
                )
            target_seconds = audio_seconds + 1.0

            weights = [
                max(
                    1,
                    len((scene.get("narration") or scene["body"]).split()),
                )
                for scene in scenes
            ]
            total_weight = sum(weights)

            image_paths = []
            concat_lines = []

            for index, scene in enumerate(scenes):
                if cancel_event and cancel_event.is_set():
                    raise VideoRenderCancelled(
                        "Video rendering was cancelled."
                    )

                image_path = work_dir / f"scene_{index:02d}.png"

                _draw_scene(
                    title=title.strip()[:90],
                    heading=scene["heading"].strip()[:100],
                    body=scene["body"].strip()[:500],
                    index=index,
                    total=len(scenes),
                    path=image_path,
                )
                image_paths.append(image_path)

                duration = max(
                    3.0,
                    target_seconds * weights[index] / total_weight,
                )

                concat_lines.append(f"file '{image_path.as_posix()}'")
                concat_lines.append(f"duration {duration:.3f}")

            # The concat demuxer needs the final image repeated.
            concat_lines.append(f"file '{image_paths[-1].as_posix()}'")
            concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

            _run_process(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_path),
                    "-i", str(audio_path),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-vf", f"fps={FPS},format=yuv420p",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-shortest",
                    "-movflags", "+faststart",
                    str(output_path),
                ],
                timeout=300,
                cancel_event=cancel_event,
            )

        if not output_path.exists() or output_path.stat().st_size < 10_000:
            raise RuntimeError("FFmpeg did not produce a valid MP4 file.")

        video_seconds = _audio_duration(
            ffprobe, output_path, cancel_event
        )
        if not 270 <= video_seconds <= 330:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Rendered MP4 duration is {video_seconds:.1f} seconds, not 4:30-5:30."
            )

        if cancel_event and cancel_event.is_set():
            raise VideoRenderCancelled("Video rendering was cancelled.")

        return {
            "filename": filename,
            "path": str(output_path),
            "url": f"/api/videos/{filename}",
            "duration_seconds": round(video_seconds, 2),
            "size_bytes": output_path.stat().st_size,
        }
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise
