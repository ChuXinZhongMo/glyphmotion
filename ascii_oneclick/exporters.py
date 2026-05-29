from __future__ import annotations

import gzip
import html
import json
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import APP_NAME
from .core import (
    AsciiAnimation,
    ConversionCancelled,
    VIDEO_EXTENSIONS,
    find_chafa,
    find_ffmpeg,
    safe_output_stem,
)


def export_many(
    animation: AsciiAnimation,
    output_dir: str | Path,
    formats: list[str],
    color: bool = True,
    ffmpeg_path: str | None = None,
    chafa_path: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_output_stem(animation.source)
    written: list[Path] = []

    fmts = [item.lower().strip() for item in formats if item.strip()]
    total = len(fmts)
    for done, fmt in enumerate(fmts, start=1):
        if should_cancel is not None and should_cancel():
            raise ConversionCancelled()
        if fmt == "txt":
            path = out_dir / f"{stem}.txt"
            export_txt(animation, path)
        elif fmt == "html":
            path = out_dir / f"{stem}.html"
            export_html(animation, path, color=color)
        elif fmt == "gif":
            path = out_dir / f"{stem}.gif"
            export_gif(animation, path, color=color)
        elif fmt == "mp4":
            path = out_dir / f"{stem}.mp4"
            export_mp4(animation, path, color=color, ffmpeg_path=ffmpeg_path)
        elif fmt == "webm":
            path = out_dir / f"{stem}.webm"
            export_webm(animation, path, color=color, ffmpeg_path=ffmpeg_path)
        elif fmt == "hevc":
            path = out_dir / f"{stem}_hevc.mp4"
            export_hevc(animation, path, color=color, ffmpeg_path=ffmpeg_path)
        elif fmt == "mov":
            path = out_dir / f"{stem}.mov"
            export_mov(animation, path, color=color, ffmpeg_path=ffmpeg_path)
        elif fmt == "av1":
            path = out_dir / f"{stem}_av1.mp4"
            export_av1(animation, path, color=color, ffmpeg_path=ffmpeg_path)
        elif fmt == "png":
            path = out_dir / f"{stem}.png"
            export_png(animation, path, color=color)
        elif fmt == "dur":
            path = out_dir / f"{stem}.dur"
            export_dur(animation, path, color=color)
        elif fmt == "ansi":
            path = out_dir / f"{stem}.ansi"
            export_ansi(animation, path, color=color, chafa_path=chafa_path)
        elif fmt in {"asciimation", "aam"}:
            path = out_dir / f"{stem}.aam"
            export_asciimation(animation, path)
        else:
            raise ValueError(f"Unknown output format: {fmt}")
        written.append(path)
        if progress is not None:
            progress(done, total, fmt)
    return written


def export_txt(animation: AsciiAnimation, path: str | Path) -> Path:
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if len(animation.frames) == 1:
            handle.write("\n".join(animation.frames[0].lines))
            handle.write("\n")
            return path

        handle.write(f"# {APP_NAME} export: {animation.source.name}\n")
        handle.write(f"# frames={len(animation.frames)} fps={animation.fps:g}\n\n")
        for index, frame in enumerate(animation.frames, start=1):
            handle.write(f"--- frame {index} duration={frame.duration:.3f}s ---\n")
            handle.write("\n".join(frame.lines))
            handle.write("\n\n")
    return path


def export_asciimation(animation: AsciiAnimation, path: str | Path) -> Path:
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"x:{animation.columns}\n")
        handle.write(f"y:{animation.rows}\n")
        handle.write(f"fps:{animation.fps:g}\n")
        handle.write("BEGIN\n")
        for index, frame in enumerate(animation.frames):
            if index:
                handle.write("\nEND\n")
            handle.write("\n".join(frame.lines))
        handle.write("\n")
    return path


def export_html(animation: AsciiAnimation, path: str | Path, color: bool = True) -> Path:
    path = Path(path)
    uses_braille = any(is_braille_frame(frame) for frame in animation.frames)
    font_family = (
        '"Segoe UI Symbol", Consolas, "Cascadia Mono", "Courier New", monospace'
        if uses_braille
        else 'Consolas, "Cascadia Mono", "Courier New", monospace'
    )
    if color:
        rendered_frames = [
            _frame_to_colored_html(frame.lines, frame.colors, frame.bg_colors) for frame in animation.frames
        ]
        render_line = "screen.innerHTML = frames[index];"
    elif uses_braille:
        rendered_frames = [_frame_to_mono_html(frame.lines) for frame in animation.frames]
        render_line = "screen.innerHTML = frames[index];"
    else:
        rendered_frames = [html.escape("\n".join(frame.lines)) for frame in animation.frames]
        render_line = "screen.textContent = frames[index];"
    durations = [max(16, int(frame.duration * 1000)) for frame in animation.frames]

    document = _html_document(
        title=f"{html.escape(APP_NAME)} - {html.escape(animation.source.name)}",
        font_family=font_family,
        frames_json=json.dumps(rendered_frames, ensure_ascii=False),
        durations_json=json.dumps(durations),
        render_line=render_line,
        default_delay=int(1000 / max(animation.fps, 1.0)),
        fps=round(max(animation.fps, 1.0), 2),
    )
    path.write_text(document, encoding="utf-8", newline="\n")
    return path


# Self-contained single-file player. CSS/JS braces are doubled for the f-string;
# the data placeholders (frames_json/durations_json) are pre-serialized so they
# never introduce stray braces.
def _html_document(
    *,
    title: str,
    font_family: str,
    frames_json: str,
    durations_json: str,
    render_line: str,
    default_delay: int,
    fps: float,
) -> str:
    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{
  margin: 0;
  min-height: 100vh;
  background: #080808;
  color: #f2f2f2;
  display: grid;
  place-items: center;
  font-family: {font_family};
}}
main {{
  width: min(96vw, max-content);
}}
pre {{
  margin: 0;
  line-height: 1;
  font-size: clamp(6px, 1vw, 13px);
  letter-spacing: 0;
  white-space: pre;
}}
pre span {{
  display: inline-block;
  width: 1ch;
}}
.bar {{
  margin-top: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
  color: #cfcfcf;
  font: 13px system-ui, sans-serif;
}}
button {{
  border: 1px solid #555;
  background: #1a1a1a;
  color: #f2f2f2;
  padding: 6px 10px;
  cursor: pointer;
}}
.info {{
  margin-left: 4px;
  color: #9aa0a6;
}}
</style>
</head>
<body>
<main>
<pre id="screen"></pre>
<div class="bar">
  <button id="toggle">暂停</button>
  <button id="replay">重播</button>
  <button id="speed">速度 1x</button>
  <span id="meta" class="info"></span>
  <span id="rate" class="info"></span>
</div>
</main>
<script>
const frames = {frames_json};
const durations = {durations_json};
const defaultDelay = {default_delay};
const baseFps = {fps};
const speeds = [0.5, 1, 2, 4];
let speedIndex = 1;
const screen = document.getElementById("screen");
const meta = document.getElementById("meta");
const rate = document.getElementById("rate");
const toggle = document.getElementById("toggle");
const replay = document.getElementById("replay");
const speedBtn = document.getElementById("speed");
let index = 0;
let playing = true;
let timer = null;
function draw() {{
  {render_line}
  meta.textContent = `${{index + 1}} / ${{frames.length}}`;
  rate.textContent = `${{(baseFps * speeds[speedIndex]).toFixed(1)}} fps`;
}}
function frameDelay() {{
  return (durations[index] || defaultDelay) / speeds[speedIndex];
}}
function schedule() {{
  if (!playing || frames.length <= 1) return;
  timer = setTimeout(() => {{
    index = (index + 1) % frames.length;
    draw();
    schedule();
  }}, frameDelay());
}}
function restart() {{
  if (timer) clearTimeout(timer);
  if (playing) schedule();
}}
toggle.addEventListener("click", () => {{
  playing = !playing;
  toggle.textContent = playing ? "暂停" : "播放";
  restart();
}});
replay.addEventListener("click", () => {{
  index = 0;
  if (!playing) {{
    playing = true;
    toggle.textContent = "暂停";
  }}
  draw();
  restart();
}});
speedBtn.addEventListener("click", () => {{
  speedIndex = (speedIndex + 1) % speeds.length;
  speedBtn.textContent = `速度 ${{speeds[speedIndex]}}x`;
  draw();
  restart();
}});
draw();
schedule();
</script>
</body>
</html>
"""


def export_png(animation: AsciiAnimation, path: str | Path, color: bool = True) -> Path:
    frame = animation.frames[0]
    image = render_frame(frame.lines, frame.colors, bg_colors=frame.bg_colors, color=color, braille=is_braille_frame(frame))
    image.save(path)
    return Path(path)


def export_gif(animation: AsciiAnimation, path: str | Path, color: bool = True) -> Path:
    images = [
        render_frame(frame.lines, frame.colors, bg_colors=frame.bg_colors, color=color, braille=is_braille_frame(frame))
        for frame in animation.frames
    ]
    durations = [max(20, int(frame.duration * 1000)) for frame in animation.frames]
    first, *rest = images
    first.save(
        path,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return Path(path)


def _export_video(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool,
    ffmpeg: str,
    *,
    vf: str,
    video_args: list[str],
    audio_args: list[str],
    post_args: list[str],
) -> Path:
    source = animation.source
    keep_audio = source.suffix.lower() in VIDEO_EXTENSIONS and source.exists()

    with tempfile.TemporaryDirectory(prefix="glyphmotion-render-") as temp_dir:
        temp = Path(temp_dir)
        for index, frame in enumerate(animation.frames, start=1):
            image = render_frame(
                frame.lines, frame.colors,
                bg_colors=frame.bg_colors, color=color,
                braille=is_braille_frame(frame),
            )
            image.save(temp / f"frame_{index:06d}.png")

        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(animation.fps),
            "-i", str(temp / "frame_%06d.png"),
        ]
        if keep_audio:
            cmd += ["-i", str(source)]
        cmd += ["-vf", vf] + video_args
        if keep_audio:
            cmd += ["-map", "0:v:0", "-map", "1:a:0?"] + audio_args + ["-shortest"]
        cmd += post_args + [str(path)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"FFmpeg failed ({Path(path).suffix}): {detail}")
    return Path(path)


def export_mp4(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool = True,
    ffmpeg_path: str | None = None,
) -> Path:
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for MP4 export but was not found.")
    return _export_video(
        animation, path, color, ffmpeg,
        vf="pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p",
        video_args=["-c:v", "libx264", "-crf", "18", "-preset", "slow"],
        audio_args=["-c:a", "aac", "-b:a", "192k"],
        post_args=["-movflags", "+faststart"],
    )


def export_webm(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool = True,
    ffmpeg_path: str | None = None,
) -> Path:
    """Export full-color WebM (VP9 + yuv444) — the widest, most faithful color.

    Unlike MP4's yuv420p, VP9 4:4:4 keeps every pixel's color (no chroma
    subsampling), so the dense colored glyphs stay as vivid as the GIF instead
    of being washed out. WebM is less universally supported than MP4 (some
    older players / platforms reject it), so it is offered alongside MP4 rather
    than replacing it.
    """
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for WebM export but was not found.")
    return _export_video(
        animation, path, color, ffmpeg,
        vf="pad=ceil(iw/2)*2:ceil(ih/2)*2",
        video_args=["-c:v", "libvpx-vp9", "-pix_fmt", "yuv444p",
                    "-crf", "20", "-b:v", "0", "-row-mt", "1", "-cpu-used", "2"],
        audio_args=["-c:a", "libopus", "-b:a", "192k"],
        post_args=[],
    )


def export_hevc(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool = True,
    ffmpeg_path: str | None = None,
) -> Path:
    """Export full-color HEVC/H.265 MP4 (yuv444p). Wider player support than WebM on Windows."""
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for HEVC export but was not found.")
    return _export_video(
        animation, path, color, ffmpeg,
        vf="pad=ceil(iw/2)*2:ceil(ih/2)*2",
        video_args=["-c:v", "libx265", "-pix_fmt", "yuv444p",
                    "-crf", "22", "-preset", "medium", "-tag:v", "hvc1"],
        audio_args=["-c:a", "aac", "-b:a", "192k"],
        post_args=["-movflags", "+faststart"],
    )


def export_mov(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool = True,
    ffmpeg_path: str | None = None,
) -> Path:
    """Export ProRes 4444 MOV — lossless-quality, full color, professional use."""
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for MOV export but was not found.")
    return _export_video(
        animation, path, color, ffmpeg,
        vf="pad=ceil(iw/2)*2:ceil(ih/2)*2",
        video_args=["-c:v", "prores_ks", "-profile:v", "4444",
                    "-pix_fmt", "yuva444p10le", "-q:v", "11"],
        audio_args=["-c:a", "aac", "-b:a", "192k"],
        post_args=[],
    )


def export_av1(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool = True,
    ffmpeg_path: str | None = None,
) -> Path:
    """Export AV1 MP4 (yuv444p10le via SVT-AV1) — best compression, full color."""
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for AV1 export but was not found.")
    return _export_video(
        animation, path, color, ffmpeg,
        vf="pad=ceil(iw/2)*2:ceil(ih/2)*2",
        video_args=["-c:v", "libsvtav1", "-pix_fmt", "yuv444p10le",
                    "-crf", "30", "-b:v", "0", "-svtav1-params", "tune=0"],
        audio_args=["-c:a", "aac", "-b:a", "192k"],
        post_args=["-movflags", "+faststart"],
    )


def export_ansi(
    animation: AsciiAnimation,
    path: str | Path,
    color: bool = True,
    chafa_path: str | None = None,
) -> Path:
    chafa = chafa_path or find_chafa()
    if chafa and animation.source.suffix.lower() not in VIDEO_EXTENSIONS:
        command = [
            chafa,
            "--format",
            "symbols",
            "--colors",
            "full" if color else "none",
            "--size",
            f"{animation.columns}x{animation.rows}",
            "--animate",
            "on",
            str(animation.source),
        ]
        completed = subprocess.run(command, capture_output=True)
        if completed.returncode == 0 and completed.stdout:
            Path(path).write_bytes(completed.stdout)
            return Path(path)

    data = bytearray()
    for index, frame in enumerate(animation.frames):
        if index:
            data.extend(b"\x1b[H")
        for y, line in enumerate(frame.lines):
            for x, char in enumerate(line):
                if color:
                    r, g, b = frame.colors[y][x]
                    data.extend(f"\x1b[38;2;{r};{g};{b}m".encode("ascii"))
                    if frame.bg_colors:
                        br, bg, bb = frame.bg_colors[y][x]
                        data.extend(f"\x1b[48;2;{br};{bg};{bb}m".encode("ascii"))
                data.extend(char.encode("utf-8"))
            data.extend(b"\x1b[0m\n")
        if index < len(animation.frames) - 1:
            data.extend(f"\n# frame delay: {frame.duration:.3f}s\n".encode("ascii"))
    Path(path).write_bytes(bytes(data))
    return Path(path)


def export_dur(animation: AsciiAnimation, path: str | Path, color: bool = True) -> Path:
    frames = []
    for index, frame in enumerate(animation.frames, start=1):
        color_map = []
        for x in range(animation.columns):
            column = []
            for y in range(animation.rows):
                fg = rgb_to_xterm256(frame.colors[y][x]) if color else 8
                bg = rgb_to_xterm256(frame.bg_colors[y][x]) if color and frame.bg_colors else 0
                column.append([fg, bg])
            color_map.append(column)
        frames.append(
            {
                "frameNumber": index,
                "delay": frame.duration,
                "contents": frame.lines,
                "colorMap": color_map,
            }
        )

    payload = {
        "DurMovie": {
            "formatVersion": 7,
            "colorFormat": "256",
            "preferredFont": "fixed",
            "encoding": "utf-8",
            "name": animation.source.stem,
            "artist": "",
            "framerate": animation.fps,
            "sizeX": animation.columns,
            "sizeY": animation.rows,
            "extra": {"createdBy": APP_NAME},
            "frames": frames,
        }
    }
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return Path(path)


def render_frame(
    lines: list[str],
    colors: list[list[tuple[int, int, int]]],
    bg_colors: list[list[tuple[int, int, int]]] | None = None,
    color: bool = True,
    font_size: int = 14,
    margin: int = 10,
    braille: bool = False,
) -> Image.Image:
    font = load_mono_font(font_size, braille=braille)
    metric_char = "⣿" if braille else "M"
    bbox = font.getbbox(metric_char)
    cell_width = max(1, int(font.getlength(metric_char)))
    line_height = max(1, bbox[3] - bbox[1] + 2)
    width = max(len(line) for line in lines) * cell_width + margin * 2
    height = len(lines) * line_height + margin * 2
    image = Image.new("RGB", (width, height), (8, 8, 8))
    draw = ImageDraw.Draw(image)

    for y, line in enumerate(lines):
        py = margin + y * line_height
        if not color:
            draw.text((margin, py), line, fill=(242, 242, 242), font=font)
            continue
        if bg_colors is not None:
            for x, char in enumerate(line):
                px = margin + x * cell_width
                draw.rectangle((px, py, px + cell_width, py + line_height), fill=bg_colors[y][x])
                if char == "▀":
                    draw.rectangle((px, py, px + cell_width, py + max(1, line_height // 2)), fill=colors[y][x])
                else:
                    draw.text((px, py), char, fill=colors[y][x], font=font)
            continue
        for x, char in enumerate(line):
            draw.text((margin + x * cell_width, py), char, fill=colors[y][x], font=font)
    return image


def load_mono_font(size: int, braille: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if braille:
        candidates.extend(
            [
                Path("C:/Windows/Fonts/seguisym.ttf"),
                Path("C:/Windows/Fonts/seguihis.ttf"),
                Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
            ]
        )
    candidates.extend([
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/CascadiaMono.ttf"),
        Path("C:/Windows/Fonts/lucon.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/System/Library/Fonts/Menlo.ttc"),
    ])
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def measure_font_aspect(size: int = 14, braille: bool = False) -> float:
    font = load_mono_font(size, braille=braille)
    metric_char = "⣿" if braille else "M"
    bbox = font.getbbox(metric_char)
    width = max(1, int(font.getlength(metric_char)))
    height = max(1, bbox[3] - bbox[1] + 2)
    return width / height


def is_braille_frame(frame) -> bool:
    for line in frame.lines:
        for char in line:
            if "\u2800" <= char <= "\u28ff":
                return True
    return False


def rgb_to_xterm256(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return round(((r - 8) / 247) * 24) + 232

    def channel(value: int) -> int:
        return round(value / 255 * 5)

    return 16 + 36 * channel(r) + 6 * channel(g) + channel(b)


def _frame_to_colored_html(
    lines: list[str],
    colors: list[list[tuple[int, int, int]]],
    bg_colors: list[list[tuple[int, int, int]]] | None = None,
) -> str:
    html_lines: list[str] = []
    for y, line in enumerate(lines):
        parts: list[str] = []
        for x, char in enumerate(line):
            escaped_char = "&nbsp;" if char == " " else html.escape(char)
            r, g, b = colors[y][x]
            if bg_colors:
                br, bg, bb = bg_colors[y][x]
                parts.append(
                    f'<span style="color:rgb({r},{g},{b});background-color:rgb({br},{bg},{bb})">'
                    f"{escaped_char}</span>"
                )
            else:
                parts.append(f'<span style="color:rgb({r},{g},{b})">{escaped_char}</span>')
        html_lines.append("".join(parts))
    return "\n".join(html_lines)


def _frame_to_mono_html(lines: list[str]) -> str:
    html_lines: list[str] = []
    for line in lines:
        html_lines.append("".join(f"<span>{'&nbsp;' if char == ' ' else html.escape(char)}</span>" for char in line))
    return "\n".join(html_lines)
