from __future__ import annotations

import colorsys
import os
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageSequence


DEFAULT_CHARSET = " .:-=+*#%@"
LONG_CHARSET = (
    "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>"
    "i!lI;:,\"^`'. "
)
BLOCK_CHARSET = "#XO+=-:. "
MINIMAL_CHARSET = " .:-=+#"
SIMPLE_CHARSET = " .-+#"
SOFT_CHARSET = "   ...,,,:::---===+++***"
RESTORE_CHARSET = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
SHADER_CHARSET = "  ..::ccooOOPP@@"
ADAPTIVE_TONE_CHARS = "   ..,,::--==++**cooOOPP@@"

CHARSETS = {
    "default": DEFAULT_CHARSET,
    "long": LONG_CHARSET,
    "blocks": BLOCK_CHARSET,
    "minimal": MINIMAL_CHARSET,
    "simple": SIMPLE_CHARSET,
    "soft": SOFT_CHARSET,
    "restore": RESTORE_CHARSET,
    "shader": SHADER_CHARSET,
    "jiejoe": "01.- ",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".wmv",
    ".webm",
    ".flv",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".3gp",
}


@dataclass(frozen=True)
class ConvertOptions:
    columns: int = 100
    fps: float = 12.0
    charset_name: str = "default"
    render_mode: str = "halfblock"
    invert: bool = False
    color: bool = True
    max_frames: int = 240
    start_time: float | None = None
    duration: float | None = None
    char_aspect: float = 0.57
    autocontrast: bool = True
    clean: bool = False
    edges: bool = False
    edge_threshold: int = 55
    hierarchy: bool = True
    hierarchy_threshold: float = 0.16
    separation: bool = True
    separation_threshold: int = 42
    detail: bool = True
    color_grade: str = "source"
    supersample: int = 1

    @property
    def charset(self) -> str:
        return CHARSETS.get(self.charset_name, self.charset_name) or DEFAULT_CHARSET


@dataclass
class AsciiFrame:
    lines: list[str]
    colors: list[list[tuple[int, int, int]]]
    duration: float
    bg_colors: list[list[tuple[int, int, int]]] | None = None


@dataclass
class AsciiAnimation:
    frames: list[AsciiFrame]
    columns: int
    rows: int
    fps: float
    source: Path

    @property
    def is_animated(self) -> bool:
        return len(self.frames) > 1


class ConversionError(RuntimeError):
    pass


def default_char_aspect() -> float:
    try:
        from .exporters import measure_font_aspect

        return measure_font_aspect()
    except Exception:
        return 0.57


def find_ffmpeg() -> str | None:
    return _find_executable(
        "ASCII_ONECLICK_FFMPEG",
        ["ffmpeg", "ffmpeg.exe"],
        [
            *_bundled_executable_candidates("ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/Git/usr/bin/ffmpeg.exe"),
        ],
        ["Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"],
    )


def find_chafa() -> str | None:
    return _find_executable(
        "ASCII_ONECLICK_CHAFA",
        ["chafa", "chafa.exe", "Chafa.exe"],
        [],
        ["hpjansson.Chafa*/chafa-*/Chafa.exe", "hpjansson.Chafa*/chafa-*/chafa.exe"],
    )


def find_ascii_image_converter() -> str | None:
    return _find_executable(
        "ASCII_ONECLICK_AIC",
        ["ascii-image-converter", "ascii-image-converter.exe"],
        [],
        ["TheZoraiz.ascii-image-converter*/ascii-image-converter*/ascii-image-converter.exe"],
    )


def _bundled_executable_candidates(name: str) -> list[Path]:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / name)
        candidates.append(Path(meipass) / "bin" / name)

    executable = getattr(sys, "executable", None)
    if executable:
        exe_dir = Path(executable).resolve().parent
        candidates.append(exe_dir / name)
        candidates.append(exe_dir / "bin" / name)

    return candidates


def _find_executable(
    env_var: str,
    names: list[str],
    explicit_candidates: list[Path],
    winget_globs: list[str],
) -> str | None:
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return override

    for name in names:
        found = shutil.which(name)
        if found:
            return found

    candidates: list[Path] = list(explicit_candidates)
    local = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if local.exists():
        for pattern in winget_globs:
            candidates.extend(local.glob(pattern))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def convert_file(
    input_path: str | Path,
    options: ConvertOptions,
    ffmpeg_path: str | None = None,
) -> AsciiAnimation:
    source = Path(input_path)
    if not source.exists():
        raise ConversionError(f"Input file not found: {source}")

    images, durations = load_media_frames(source, options, ffmpeg_path)
    if not images:
        raise ConversionError("No frames were decoded from the input file.")

    frames = [image_to_ascii(img, duration, options) for img, duration in zip(images, durations)]
    rows = len(frames[0].lines)
    columns = len(frames[0].lines[0]) if rows else 0
    return AsciiAnimation(frames=frames, columns=columns, rows=rows, fps=options.fps, source=source)


def load_media_frames(
    source: Path,
    options: ConvertOptions,
    ffmpeg_path: str | None = None,
) -> tuple[list[Image.Image], list[float]]:
    try:
        with Image.open(source) as image:
            if getattr(image, "is_animated", False):
                return _load_animated_image(image, options)
            return [image.convert("RGB")], [1.0 / max(options.fps, 1.0)]
    except Exception:
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ConversionError(f"Unsupported or unreadable input file: {source}")
        return _load_video_frames(source, options, ffmpeg_path)


def _load_animated_image(
    image: Image.Image,
    options: ConvertOptions,
) -> tuple[list[Image.Image], list[float]]:
    frames: list[Image.Image] = []
    durations: list[float] = []
    count = min(getattr(image, "n_frames", 1), options.max_frames)

    for index, frame in enumerate(ImageSequence.Iterator(image)):
        if index >= count:
            break
        duration_ms = frame.info.get("duration", int(1000 / max(options.fps, 1.0)))
        frames.append(frame.convert("RGB"))
        durations.append(max(duration_ms / 1000.0, 1.0 / max(options.fps, 1.0)))
    return frames, durations


def _load_video_frames(
    source: Path,
    options: ConvertOptions,
    ffmpeg_path: str | None = None,
) -> tuple[list[Image.Image], list[float]]:
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if not ffmpeg:
        raise ConversionError("FFmpeg is required for video input but was not found.")

    with tempfile.TemporaryDirectory(prefix="glyphmotion-frames-") as temp_dir:
        frame_pattern = str(Path(temp_dir) / "frame_%06d.png")
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        if options.start_time is not None:
            command.extend(["-ss", str(options.start_time)])
        command.extend(["-i", str(source)])
        if options.duration is not None:
            command.extend(["-t", str(options.duration)])
        command.extend(
            [
                "-vf",
                f"fps={options.fps}",
                "-frames:v",
                str(options.max_frames),
                frame_pattern,
            ]
        )

        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ConversionError(f"FFmpeg failed to decode video frames: {detail}")

        paths = sorted(Path(temp_dir).glob("frame_*.png"))
        images = [Image.open(path).convert("RGB") for path in paths]
        duration = 1.0 / max(options.fps, 1.0)
        return images, [duration] * len(images)


def image_to_ascii(image: Image.Image, duration: float, options: ConvertOptions) -> AsciiFrame:
    if options.render_mode == "braille":
        return image_to_braille(image, duration, options)
    if options.render_mode == "adaptive":
        return image_to_adaptive_ascii(image, duration, options)
    if options.charset_name == "shader":
        return image_to_shader_ascii(image, duration, options)
    if options.render_mode == "fullblock":
        return image_to_fullblock(image, duration, options)
    if options.render_mode == "halfblock":
        return image_to_halfblock(image, duration, options)

    source = image.convert("RGB")
    if options.detail:
        source = source.filter(ImageFilter.UnsharpMask(radius=1.1, percent=135, threshold=3))
    if options.clean:
        radius = 0.25 if options.detail else 0.75
        source = source.filter(ImageFilter.GaussianBlur(radius=radius))
    width, height = source.size
    columns = max(8, options.columns)
    rows = max(1, int((height / width) * columns * options.char_aspect))

    resized_rgb = source.resize((columns, rows), Image.Resampling.LANCZOS)
    if options.clean:
        resized_rgb = resized_rgb.filter(ImageFilter.SMOOTH_MORE)
    gray = resized_rgb.convert("L")
    if options.autocontrast:
        cutoff = 1 if options.detail else 0
        gray = ImageOps.autocontrast(gray, cutoff=cutoff)
    if options.clean:
        gray = gray.filter(ImageFilter.MedianFilter(size=3))
    saliency = build_saliency_map(gray) if options.hierarchy else None
    separators = build_separator_map(gray, threshold=options.separation_threshold) if options.separation else None
    charset = options.charset[::-1] if options.invert else options.charset
    max_index = len(charset) - 1
    jiejoe_levels = [["0", "1"], [".", "-"], [" "]]
    if options.invert:
        jiejoe_levels = list(reversed(jiejoe_levels))

    lines: list[str] = []
    colors: list[list[tuple[int, int, int]]] = []
    for y in range(rows):
        chars: list[str] = []
        color_row: list[tuple[int, int, int]] = []
        for x in range(columns):
            value = gray.getpixel((x, y))
            if options.charset_name == "jiejoe":
                level_index = min(len(jiejoe_levels) - 1, int((value / 255) * len(jiejoe_levels)))
                chars.append(jiejoe_levels[level_index][0] if options.clean else random.choice(jiejoe_levels[level_index]))
                color_row.append((23, 247, 0))
                continue

            if separators is not None and separators[y][x]:
                chars.append(" " if options.clean else ".")
                sep_value = 38 if not options.invert else 205
                color_row.append((sep_value, sep_value, sep_value))
                continue

            if saliency is not None:
                importance = saliency[y][x]
                if importance < options.hierarchy_threshold:
                    chars.append(" " if importance < options.hierarchy_threshold * 0.65 else ".")
                    bg_value = 62 if not options.invert else 190
                    color_row.append((bg_value, bg_value, bg_value))
                    continue
                value = blend_toward_contrast(value, importance)

            edge_char = edge_character(gray, x, y, threshold=options.edge_threshold) if options.edges else None
            if edge_char:
                chars.append(edge_char)
                edge_value = 230 if not options.invert else 40
                color_row.append((edge_value, edge_value, edge_value))
                continue

            if options.clean:
                levels = min(max_index + 1, 12 if options.detail else 5)
                value = quantize_value(value, levels=levels)
            char_index = round((value / 255) * max_index)
            chars.append(charset[char_index])
            rgb = resized_rgb.getpixel((x, y))
            if options.color:
                color_row.append(quantize_rgb(rgb, levels=5) if options.clean else rgb)
            else:
                v = quantize_value(value, levels=5) if options.clean else value
                color_row.append((v, v, v))
        lines.append("".join(chars))
        colors.append(color_row)

    return AsciiFrame(lines=lines, colors=colors, duration=duration)


def image_to_braille(image: Image.Image, duration: float, options: ConvertOptions) -> AsciiFrame:
    source = image.convert("RGB")
    if options.detail:
        source = source.filter(ImageFilter.UnsharpMask(radius=1.0, percent=125, threshold=3))
    if options.clean:
        source = source.filter(ImageFilter.GaussianBlur(radius=0.12))

    width, height = source.size
    columns = max(8, options.columns)
    rows = max(1, int((height / width) * columns * braille_char_aspect()))
    sample_width = columns * 2
    sample_height = rows * 4

    sampled_rgb = source.resize((sample_width, sample_height), Image.Resampling.LANCZOS)
    gray = sampled_rgb.convert("L")
    if options.autocontrast:
        gray = ImageOps.autocontrast(gray, cutoff=1)

    lines: list[str] = []
    colors: list[list[tuple[int, int, int]]] = []
    for y in range(rows):
        chars: list[str] = []
        color_row: list[tuple[int, int, int]] = []
        for x in range(columns):
            x0 = x * 2
            y0 = y * 4
            threshold = average_luma(gray, x0, y0, 4)
            dot_mask = 0
            active_pixels: list[tuple[int, int]] = []
            for dy in range(4):
                for dx in range(2):
                    px = x0 + dx
                    py = y0 + dy
                    value = gray.getpixel((px, py))
                    active = value >= threshold if not options.invert else value < threshold
                    if active:
                        dot_mask |= braille_dot_bit(dx, dy)
                        active_pixels.append((px, py))

            chars.append(chr(0x2800 + dot_mask) if dot_mask else " ")
            color_row.append(
                average_active_rgb(sampled_rgb, active_pixels)
                if options.color and active_pixels
                else ((230, 230, 230) if not options.invert else (45, 45, 45))
            )
        lines.append("".join(chars))
        colors.append(color_row)

    return AsciiFrame(lines=lines, colors=colors, duration=duration)


def image_to_adaptive_ascii(image: Image.Image, duration: float, options: ConvertOptions) -> AsciiFrame:
    source = image.convert("RGB")
    if options.detail:
        source = source.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3))
    if options.clean:
        source = source.filter(ImageFilter.GaussianBlur(radius=0.12))

    width, height = source.size
    columns = max(8, options.columns)
    rows = max(1, int((height / width) * columns * adaptive_char_aspect()))

    ss = max(1, min(4, options.supersample))
    patch_width = 2 * ss
    patch_height = 4 * ss
    sampled_rgb = source.resize((columns * patch_width, rows * patch_height), Image.Resampling.LANCZOS)
    raw_gray = sampled_rgb.convert("L")
    gray = ImageOps.autocontrast(raw_gray, cutoff=1) if options.autocontrast else raw_gray
    cell_gray = gray.resize((columns, rows), Image.Resampling.LANCZOS)

    saliency = build_saliency_map(cell_gray) if options.hierarchy else None
    separators = build_separator_map(cell_gray, threshold=options.separation_threshold) if options.separation else None

    lines: list[str] = []
    colors: list[list[tuple[int, int, int]]] = []
    for y in range(rows):
        chars: list[str] = []
        color_row: list[tuple[int, int, int]] = []
        for x in range(columns):
            x0 = x * patch_width
            y0 = y * patch_height
            mean, contrast, stddev, dx, dy = patch_luma_stats(gray, x0, y0, patch_width, patch_height)
            raw_mean = average_luma_rect(raw_gray, x0, y0, patch_width, patch_height)
            importance = saliency[y][x] if saliency is not None else 1.0
            separator = bool(separators and separators[y][x])
            dot_mask, dot_count = adaptive_braille_mask(
                gray,
                x0,
                y0,
                ss,
                mean,
                contrast,
                invert=options.invert,
            )

            char, background = choose_adaptive_char(
                mean=mean,
                contrast=contrast,
                stddev=stddev,
                dx=dx,
                dy=dy,
                importance=importance,
                separator=separator,
                dot_mask=dot_mask,
                dot_count=dot_count,
                options=options,
            )
            chars.append(char)

            rgb = average_rgb_rect(sampled_rgb, x0, y0, patch_width, patch_height)
            if options.color:
                color_row.append(adaptive_tone(rgb, raw_mean, importance, contrast, background, options.color_grade))
            else:
                value = adaptive_mono_value(raw_mean, importance, contrast, background)
                color_row.append((value, value, value))
        lines.append("".join(chars))
        colors.append(color_row)

    return AsciiFrame(lines=lines, colors=colors, duration=duration)


def adaptive_char_aspect() -> float:
    try:
        from .exporters import measure_font_aspect

        return measure_font_aspect(braille=True)
    except Exception:
        return 0.65


def patch_luma_stats(
    gray: Image.Image,
    x0: int,
    y0: int,
    width: int,
    height: int,
) -> tuple[int, int, float, float, float]:
    total = 0
    total_sq = 0
    count = 0
    min_value = 255
    max_value = 0
    left_total = right_total = top_total = bottom_total = 0
    left_count = right_count = top_count = bottom_count = 0

    image_width, image_height = gray.size
    x1 = min(x0 + width, image_width)
    y1 = min(y0 + height, image_height)
    half_x = x0 + width / 2
    half_y = y0 + height / 2

    for py in range(y0, y1):
        for px in range(x0, x1):
            value = gray.getpixel((px, py))
            total += value
            total_sq += value * value
            count += 1
            min_value = min(min_value, value)
            max_value = max(max_value, value)
            if px < half_x:
                left_total += value
                left_count += 1
            else:
                right_total += value
                right_count += 1
            if py < half_y:
                top_total += value
                top_count += 1
            else:
                bottom_total += value
                bottom_count += 1

    count = max(1, count)
    mean = total / count
    variance = max(0.0, total_sq / count - mean * mean)
    left_mean = left_total / max(1, left_count)
    right_mean = right_total / max(1, right_count)
    top_mean = top_total / max(1, top_count)
    bottom_mean = bottom_total / max(1, bottom_count)
    return int(mean), max_value - min_value, variance**0.5, right_mean - left_mean, bottom_mean - top_mean


def average_rgb_rect(
    image: Image.Image,
    x0: int,
    y0: int,
    width: int,
    height: int,
) -> tuple[int, int, int]:
    total_r = total_g = total_b = 0
    count = 0
    image_width, image_height = image.size
    for py in range(y0, min(y0 + height, image_height)):
        for px in range(x0, min(x0 + width, image_width)):
            r, g, b = image.getpixel((px, py))
            total_r += r
            total_g += g
            total_b += b
            count += 1
    count = max(1, count)
    return total_r // count, total_g // count, total_b // count


def average_luma_rect(gray: Image.Image, x0: int, y0: int, width: int, height: int) -> int:
    total = 0
    count = 0
    image_width, image_height = gray.size
    for py in range(y0, min(y0 + height, image_height)):
        for px in range(x0, min(x0 + width, image_width)):
            total += gray.getpixel((px, py))
            count += 1
    return total // max(1, count)


def adaptive_braille_mask(
    gray: Image.Image,
    x0: int,
    y0: int,
    sample_scale: int,
    mean: int,
    contrast: int,
    invert: bool = False,
) -> tuple[int, int]:
    threshold = mean + contrast * 0.04
    if invert:
        threshold = mean - contrast * 0.04

    dot_mask = 0
    dot_count = 0
    for dy in range(4):
        for dx in range(2):
            value = average_luma_rect(
                gray,
                x0 + dx * sample_scale,
                y0 + dy * sample_scale,
                sample_scale,
                sample_scale,
            )
            active = value >= threshold if not invert else value <= threshold
            if active:
                dot_mask |= braille_dot_bit(dx, dy)
                dot_count += 1
    return dot_mask, dot_count


def choose_adaptive_char(
    *,
    mean: int,
    contrast: int,
    stddev: float,
    dx: float,
    dy: float,
    importance: float,
    separator: bool,
    dot_mask: int,
    dot_count: int,
    options: ConvertOptions,
) -> tuple[str, bool]:
    visual = 255 - mean if options.invert else mean
    background = options.hierarchy and importance < options.hierarchy_threshold

    if separator:
        return (" " if visual < 130 else "."), True

    if background:
        if contrast < 28:
            if visual < 95:
                return " ", True
            return ("." if visual < 175 else ","), True
        return ("." if visual < 165 else ":"), True

    if options.edges and contrast >= max(options.edge_threshold, 76):
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        if abs_dx > abs_dy * 1.8:
            return "|", False
        if abs_dy > abs_dx * 1.8:
            return "-", False

    braille_ready = (
        options.detail
        and contrast >= 46
        and stddev >= 17
        and importance >= options.hierarchy_threshold * 0.85
        and dot_count >= 2
        and not (dot_count <= 2 and visual < 110)
    )
    if braille_ready and dot_mask:
        return chr(0x2800 + dot_mask), False

    return adaptive_tone_char(visual, contrast, importance), False


def adaptive_tone_char(visual: int, contrast: int, importance: float) -> str:
    value = max(0, min(255, visual))
    if contrast < 22:
        value = int(value * 0.78)
    elif contrast < 44:
        value = int(value * 0.88)
    if importance > 0.34:
        value = min(255, int(value * (1.0 + min(0.18, importance * 0.22))))
    index = round((value / 255) * (len(ADAPTIVE_TONE_CHARS) - 1))
    return ADAPTIVE_TONE_CHARS[index]


def adaptive_tone(
    rgb: tuple[int, int, int],
    luminance: int,
    importance: float,
    contrast: int,
    background: bool,
    grade: str,
) -> tuple[int, int, int]:
    if grade == "warm":
        return shader_tone(rgb, luminance, grade=grade)
    if grade == "vivid":
        return vivid_source_color_tone(
            rgb,
            luminance,
            importance=importance,
            contrast=contrast,
            background=background,
        )

    if background:
        strength = 0.22 + (luminance / 255.0) * 0.25
    else:
        strength = 0.86 + min(0.26, importance * 0.46)
        if contrast > 70:
            strength += 0.08

    r, g, b = rgb
    return clamp_color(r * strength), clamp_color(g * strength), clamp_color(b * strength)


def adaptive_mono_value(luminance: int, importance: float, contrast: int, background: bool) -> int:
    if background:
        return clamp_color(luminance * 0.45)
    strength = 0.86 + min(0.22, importance * 0.38)
    if contrast > 70:
        strength += 0.08
    return clamp_color(luminance * strength)


def braille_dot_bit(dx: int, dy: int) -> int:
    mapping = {
        (0, 0): 0x01,
        (0, 1): 0x02,
        (0, 2): 0x04,
        (0, 3): 0x40,
        (1, 0): 0x08,
        (1, 1): 0x10,
        (1, 2): 0x20,
        (1, 3): 0x80,
    }
    return mapping[(dx, dy)]


def braille_char_aspect() -> float:
    try:
        from .exporters import measure_font_aspect

        # The 2x4 dot grid increases precision inside a rendered character
        # cell; the displayed aspect is still governed by the font's cell
        # width/height.
        return measure_font_aspect(braille=True)
    except Exception:
        return 1.0


def average_active_rgb(image: Image.Image, points: list[tuple[int, int]]) -> tuple[int, int, int]:
    total_r = total_g = total_b = 0
    for x, y in points:
        r, g, b = image.getpixel((x, y))
        total_r += r
        total_g += g
        total_b += b
    count = max(1, len(points))
    return total_r // count, total_g // count, total_b // count


def image_to_shader_ascii(image: Image.Image, duration: float, options: ConvertOptions) -> AsciiFrame:
    source = image.convert("RGB")
    source = source.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=4))
    if options.clean:
        source = source.filter(ImageFilter.GaussianBlur(radius=0.18))

    width, height = source.size
    columns = max(8, options.columns)
    rows = max(1, int((height / width) * columns * options.char_aspect))

    ss = max(1, min(4, options.supersample))
    sample_columns = columns * ss
    sample_rows = rows * ss
    sampled_rgb = source.resize((sample_columns, sample_rows), Image.Resampling.LANCZOS)
    resized_rgb = sampled_rgb.resize((columns, rows), Image.Resampling.LANCZOS)
    gray = sampled_rgb.convert("L")
    if options.autocontrast:
        gray = ImageOps.autocontrast(gray, cutoff=1)

    charset = options.charset[::-1] if options.invert else options.charset
    max_index = len(charset) - 1
    lines: list[str] = []
    colors: list[list[tuple[int, int, int]]] = []

    for y in range(rows):
        chars: list[str] = []
        color_row: list[tuple[int, int, int]] = []
        for x in range(columns):
            value = average_luma(gray, x * ss, y * ss, ss)
            if ss <= 1:
                value = quantize_value(value, levels=min(max_index + 1, 10))
            char_index = round((value / 255) * max_index)
            chars.append(charset[char_index])

            r, g, b = average_rgb(sampled_rgb, x * ss, y * ss, ss)
            color_row.append(shader_tone((r, g, b), value, grade=options.color_grade))
        lines.append("".join(chars))
        colors.append(color_row)

    return AsciiFrame(lines=lines, colors=colors, duration=duration)


def average_luma(gray: Image.Image, x0: int, y0: int, size: int) -> int:
    total = 0
    count = 0
    width, height = gray.size
    for y in range(y0, min(y0 + size, height)):
        for x in range(x0, min(x0 + size, width)):
            total += gray.getpixel((x, y))
            count += 1
    return total // max(1, count)


def average_rgb(image: Image.Image, x0: int, y0: int, size: int) -> tuple[int, int, int]:
    total_r = total_g = total_b = 0
    count = 0
    width, height = image.size
    for y in range(y0, min(y0 + size, height)):
        for x in range(x0, min(x0 + size, width)):
            r, g, b = image.getpixel((x, y))
            total_r += r
            total_g += g
            total_b += b
            count += 1
    count = max(1, count)
    return total_r // count, total_g // count, total_b // count


def shader_tone(rgb: tuple[int, int, int], luminance: int, grade: str = "source") -> tuple[int, int, int]:
    r, g, b = rgb
    if grade == "source":
        return source_color_tone(
            rgb,
            luminance,
            exposure=1.28,
            saturation=1.24,
            min_value=0.46,
            visibility=1.0,
        )

    strength = 0.28 + (luminance / 255.0) * 0.86
    if grade == "warm":
        # Optional amber/game-postprocess grade.
        r = int(r * 1.08 + 18)
        g = int(g * 0.88 + 10)
        b = int(b * 0.62)
        strength = 0.42 + (luminance / 255.0) * 0.70
    return (
        clamp_color(r * strength),
        clamp_color(g * strength),
        clamp_color(b * strength),
    )


def source_color_tone(
    rgb: tuple[int, int, int],
    luminance: int,
    *,
    exposure: float,
    saturation: float,
    min_value: float,
    visibility: float,
) -> tuple[int, int, int]:
    r, g, b = rgb
    red = r / 255.0
    green = g / 255.0
    blue = b / 255.0
    hue, sat, value = colorsys.rgb_to_hsv(red, green, blue)
    luma = max(0.0, min(1.0, luminance / 255.0))

    if sat > 0.04:
        sat = min(1.0, sat * saturation + 0.03)
    floor = min(0.92, min_value + luma * 0.18)
    value = max(value, floor)
    value = min(1.0, value * exposure + luma * 0.06)

    red, green, blue = colorsys.hsv_to_rgb(hue, sat, value)
    return (
        clamp_color(red * 255 * visibility),
        clamp_color(green * 255 * visibility),
        clamp_color(blue * 255 * visibility),
    )


def vivid_source_color_tone(
    rgb: tuple[int, int, int],
    luminance: int,
    *,
    importance: float,
    contrast: int,
    background: bool,
) -> tuple[int, int, int]:
    r, g, b = rgb
    red = r / 255.0
    green = g / 255.0
    blue = b / 255.0
    hue, sat, value = colorsys.rgb_to_hsv(red, green, blue)
    luma = max(0.0, min(1.0, luminance / 255.0))

    # Preserve the source hue. Boost only existing chroma so gray/skin/shadow
    # areas do not become artificial neon colors.
    if sat > 0.05:
        sat_boost = 1.10 + (1.0 - sat) * 0.28
        sat = min(1.0, sat * sat_boost)

    if background:
        value = min(1.0, (value**0.96) * (0.90 + luma * 0.10))
        visibility = 0.70
    else:
        exposure = 1.08 + min(0.12, importance * 0.18)
        if contrast > 70:
            exposure += 0.04
        value = min(1.0, (value**0.86) * exposure + luma * 0.035)
        visibility = 1.0

    red, green, blue = colorsys.hsv_to_rgb(hue, sat, value)
    return (
        clamp_color(red * 255 * visibility),
        clamp_color(green * 255 * visibility),
        clamp_color(blue * 255 * visibility),
    )


def clamp_color(value: float) -> int:
    return max(0, min(255, int(value)))


def build_separator_map(gray: Image.Image, threshold: int = 42) -> list[list[bool]]:
    width, height = gray.size
    result = [[False for _ in range(width)] for _ in range(height)]
    gradients: list[tuple[int, int, int]] = []

    for y in range(1, height - 1):
        for x in range(1, width - 1):
            center = gray.getpixel((x, y))
            left = gray.getpixel((x - 1, y))
            right = gray.getpixel((x + 1, y))
            up = gray.getpixel((x, y - 1))
            down = gray.getpixel((x, y + 1))
            gradient = abs(right - left) + abs(down - up)
            local_range = max(center, left, right, up, down) - min(center, left, right, up, down)
            if gradient >= threshold and local_range >= threshold // 2:
                gradients.append((gradient, x, y))

    if not gradients:
        return result

    gradients.sort(reverse=True)
    max_count = max(1, (width * height) // 28)
    for _, x, y in gradients[:max_count]:
        if should_separate(gray, x, y):
            result[y][x] = True

    return result


def should_separate(gray: Image.Image, x: int, y: int) -> bool:
    center = gray.getpixel((x, y))
    horizontal_gap = abs(gray.getpixel((x - 1, y)) - center) + abs(gray.getpixel((x + 1, y)) - center)
    vertical_gap = abs(gray.getpixel((x, y - 1)) - center) + abs(gray.getpixel((x, y + 1)) - center)
    return max(horizontal_gap, vertical_gap) > 70


def build_saliency_map(gray: Image.Image) -> list[list[float]]:
    width, height = gray.size
    values = list(gray.getdata())
    mean = sum(values) / max(1, len(values))
    max_distance = ((width / 2) ** 2 + (height / 2) ** 2) ** 0.5 or 1.0
    result: list[list[float]] = []

    for y in range(height):
        row: list[float] = []
        for x in range(width):
            value = gray.getpixel((x, y))
            if x <= 0 or y <= 0 or x >= width - 1 or y >= height - 1:
                gradient = 0
            else:
                gradient = abs(gray.getpixel((x + 1, y)) - gray.getpixel((x - 1, y)))
                gradient += abs(gray.getpixel((x, y + 1)) - gray.getpixel((x, y - 1)))

            contrast = abs(value - mean)
            dx = x - width / 2
            dy = y - height / 2
            center = max(0.0, 1.0 - ((dx * dx + dy * dy) ** 0.5 / max_distance))
            score = (gradient / 510.0) * 0.58 + (contrast / 255.0) * 0.30 + center * 0.12
            row.append(min(1.0, score))
        result.append(row)
    return result


def blend_toward_contrast(value: int, importance: float) -> int:
    factor = min(1.0, max(0.0, (importance - 0.20) / 0.55))
    if value >= 128:
        return int(value + (255 - value) * factor * 0.35)
    return int(value * (1.0 - factor * 0.35))


def edge_character(gray: Image.Image, x: int, y: int, threshold: int = 55) -> str | None:
    width, height = gray.size
    if x <= 0 or y <= 0 or x >= width - 1 or y >= height - 1:
        return None

    left = gray.getpixel((x - 1, y))
    right = gray.getpixel((x + 1, y))
    up = gray.getpixel((x, y - 1))
    down = gray.getpixel((x, y + 1))
    dx = right - left
    dy = down - up
    magnitude = abs(dx) + abs(dy)
    if magnitude < threshold:
        return None

    abs_dx = abs(dx)
    abs_dy = abs(dy)
    if abs_dx > abs_dy * 1.8:
        return "|"
    if abs_dy > abs_dx * 1.8:
        return "-"
    return "\\" if dx * dy > 0 else "/"


def image_to_fullblock(image: Image.Image, duration: float, options: ConvertOptions) -> AsciiFrame:
    source = image.convert("RGB")
    if options.clean:
        source = source.filter(ImageFilter.GaussianBlur(radius=0.45))

    width, height = source.size
    columns = max(8, options.columns)
    rows = max(1, int((height / width) * columns * options.char_aspect))

    resized = source.resize((columns, rows), Image.Resampling.LANCZOS)
    if options.autocontrast:
        resized = ImageOps.autocontrast(resized)
    if options.clean:
        resized = resized.filter(ImageFilter.SMOOTH_MORE)
    if not options.color:
        resized = resized.convert("L").convert("RGB")

    lines: list[str] = []
    colors: list[list[tuple[int, int, int]]] = []
    for y in range(rows):
        color_row: list[tuple[int, int, int]] = []
        for x in range(columns):
            rgb = resized.getpixel((x, y))
            color_row.append(quantize_rgb(rgb, levels=8) if options.clean else rgb)
        lines.append("█" * columns)
        colors.append(color_row)

    return AsciiFrame(lines=lines, colors=colors, duration=duration)


def image_to_halfblock(image: Image.Image, duration: float, options: ConvertOptions) -> AsciiFrame:
    source = image.convert("RGB")
    if options.clean:
        source = source.filter(ImageFilter.GaussianBlur(radius=0.45))

    width, height = source.size
    columns = max(8, options.columns)
    rows = max(1, int((height / width) * columns * options.char_aspect))
    sample_height = rows * 2

    resized = source.resize((columns, sample_height), Image.Resampling.LANCZOS)
    if options.autocontrast:
        resized = ImageOps.autocontrast(resized)
    if options.clean:
        resized = resized.filter(ImageFilter.SMOOTH_MORE)
    if not options.color:
        resized = resized.convert("L").convert("RGB")

    lines: list[str] = []
    colors: list[list[tuple[int, int, int]]] = []
    bg_colors: list[list[tuple[int, int, int]]] = []
    for row in range(rows):
        line_chars: list[str] = []
        fg_row: list[tuple[int, int, int]] = []
        bg_row: list[tuple[int, int, int]] = []
        top_y = row * 2
        bottom_y = min(top_y + 1, sample_height - 1)
        for x in range(columns):
            top = resized.getpixel((x, top_y))
            bottom = resized.getpixel((x, bottom_y))
            if options.clean:
                top = quantize_rgb(top, levels=8)
                bottom = quantize_rgb(bottom, levels=8)
            line_chars.append("▀")
            fg_row.append(top)
            bg_row.append(bottom)
        lines.append("".join(line_chars))
        colors.append(fg_row)
        bg_colors.append(bg_row)

    return AsciiFrame(lines=lines, colors=colors, duration=duration, bg_colors=bg_colors)


def quantize_value(value: int, levels: int = 6) -> int:
    levels = max(2, levels)
    return round(value / 255 * (levels - 1)) * 255 // (levels - 1)


def quantize_rgb(rgb: tuple[int, int, int], levels: int = 6) -> tuple[int, int, int]:
    return tuple(quantize_value(channel, levels) for channel in rgb)


def safe_output_stem(path: Path) -> str:
    stem = path.stem.strip() or "ascii-output"
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)
