from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME
from .core import (
    CHARSETS,
    ConversionError,
    ConvertOptions,
    convert_file,
    default_char_aspect,
    find_ascii_image_converter,
    find_chafa,
    find_ffmpeg,
)
from .exporters import export_many


DEFAULT_FORMATS = "txt,html,gif,png,dur,asciimation"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyphmotion",
        description=f"{APP_NAME}: convert images, GIFs, and videos into character-art animations.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Input image, GIF, or video file. Optional when using --tools.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="Directory for generated files. Default: output",
    )
    parser.add_argument(
        "-f",
        "--formats",
        default=DEFAULT_FORMATS,
        help=f"Comma-separated output formats. Default: {DEFAULT_FORMATS}",
    )
    parser.add_argument("-w", "--width", type=int, default=100, help="ASCII output columns.")
    parser.add_argument("--fps", type=float, default=12.0, help="Animation frame rate.")
    parser.add_argument("--max-frames", type=int, default=240, help="Maximum frames to decode.")
    parser.add_argument(
        "--aspect",
        type=float,
        default=None,
        help="Character width/height correction. Increase if output looks too flat; decrease if too tall.",
    )
    parser.add_argument(
        "--charset",
        default="default",
        help=f"Charset name ({', '.join(CHARSETS)}) or a custom dark-to-light string.",
    )
    parser.add_argument(
        "--mode",
        choices=["braille", "adaptive", "fullblock", "halfblock", "ascii"],
        default="ascii",
        help="Render mode. adaptive uses the first mixed-character renderer; braille uses 2x4 dot cells; fullblock/halfblock are Unicode block-art modes.",
    )
    parser.add_argument("--invert", action="store_true", help="Invert brightness mapping.")
    parser.add_argument("--no-autocontrast", action="store_true", help="Disable contrast enhancement for character mapping.")
    parser.add_argument("--clean", action="store_true", help="Reduce visual noise with smoothing and brightness/color quantization.")
    parser.add_argument("--no-edges", action="store_true", help="Disable ASCII edge enhancement.")
    parser.add_argument("--edge-threshold", type=int, default=55, help="Edge threshold for ASCII mode. Lower means more outlines.")
    parser.add_argument("--no-hierarchy", action="store_true", help="Disable subject/background hierarchy suppression.")
    parser.add_argument("--hierarchy-threshold", type=float, default=0.16, help="Higher values suppress more background detail.")
    parser.add_argument("--no-separation", action="store_true", help="Disable soft separation gaps between visual regions.")
    parser.add_argument("--separation-threshold", type=int, default=42, help="Higher values create fewer separation gaps.")
    parser.add_argument("--no-detail", action="store_true", help="Disable unsharp/detail restoration.")
    parser.add_argument("--supersample", type=int, default=1, help="Shader ASCII supersampling. 2 is sharper but slower.")
    parser.add_argument("--mono", action="store_true", help="Disable color output.")
    parser.add_argument("--start", type=float, default=None, help="Video start time in seconds.")
    parser.add_argument("--duration", type=float, default=None, help="Video duration in seconds.")
    parser.add_argument("--ffmpeg", default=None, help="Path to ffmpeg executable.")
    parser.add_argument("--chafa", default=None, help="Path to chafa executable.")
    parser.add_argument("--tools", action="store_true", help="Print detected external tools and exit.")
    parser.add_argument(
        "--shader-color",
        action="store_true",
        help="Shortcut for source-color shader-style ASCII: --preset shader-color.",
    )
    parser.add_argument(
        "--preset",
        choices=[
            "restore",
            "shader-mono",
            "shader-color",
            "shader-color-hd",
            "adaptive-mono",
            "adaptive-color",
            "adaptive-vivid",
            "braille-mono",
            "braille-color",
            "shader-warm",
            "soft",
        ],
        default=None,
        help="Apply a predefined look. shader-mono and shader-color are separate presets.",
    )
    return parser


def build_options(args: argparse.Namespace) -> ConvertOptions:
    """Resolve parsed CLI arguments (including presets) into ConvertOptions.

    Extracted from main() so preset/option mapping can be unit tested without
    running an actual conversion.
    """
    preset = "shader-color" if args.shader_color else args.preset
    charset_name = args.charset
    render_mode = args.mode
    mono = args.mono
    hierarchy = not args.no_hierarchy
    separation = not args.no_separation
    detail = not args.no_detail
    clean = args.clean
    edges = not args.no_edges
    color_grade = "source"
    supersample = max(1, args.supersample)

    if preset == "restore":
        charset_name = "restore"
        render_mode = "ascii"
        mono = True
        hierarchy = True
        separation = False
        detail = True
        clean = True
        edges = False
    elif preset == "shader-mono":
        charset_name = "shader"
        render_mode = "ascii"
        mono = True
        hierarchy = False
        separation = False
        detail = True
        clean = True
        edges = False
    elif preset == "shader-color":
        charset_name = "shader"
        render_mode = "ascii"
        mono = False
        hierarchy = False
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "source"
        supersample = max(supersample, 1)
    elif preset == "shader-color-hd":
        charset_name = "shader"
        render_mode = "ascii"
        mono = False
        hierarchy = False
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "source"
        supersample = max(supersample, 2)
    elif preset == "adaptive-mono":
        charset_name = "shader"
        render_mode = "adaptive"
        mono = True
        hierarchy = True
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "source"
        supersample = max(supersample, 2)
    elif preset == "adaptive-color":
        charset_name = "shader"
        render_mode = "adaptive"
        mono = False
        hierarchy = True
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "source"
        supersample = max(supersample, 2)
    elif preset == "adaptive-vivid":
        charset_name = "shader"
        render_mode = "adaptive"
        mono = False
        hierarchy = True
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "vivid"
        supersample = max(supersample, 2)
    elif preset == "braille-mono":
        charset_name = "shader"
        render_mode = "braille"
        mono = True
        hierarchy = False
        separation = False
        detail = True
        clean = True
        edges = False
    elif preset == "braille-color":
        charset_name = "shader"
        render_mode = "braille"
        mono = False
        hierarchy = False
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "source"
    elif preset == "shader-warm":
        charset_name = "shader"
        render_mode = "ascii"
        mono = False
        hierarchy = False
        separation = False
        detail = True
        clean = True
        edges = False
        color_grade = "warm"
    elif preset == "soft":
        charset_name = "soft"
        render_mode = "ascii"
        mono = True
        hierarchy = True
        separation = False
        detail = False
        clean = True
        edges = False

    return ConvertOptions(
        columns=args.width,
        fps=args.fps,
        charset_name=charset_name,
        render_mode=render_mode,
        invert=args.invert,
        color=not mono,
        max_frames=args.max_frames,
        start_time=args.start,
        duration=args.duration,
        char_aspect=args.aspect if args.aspect is not None else default_char_aspect(),
        autocontrast=not args.no_autocontrast,
        clean=clean,
        edges=edges,
        edge_threshold=args.edge_threshold,
        hierarchy=hierarchy,
        hierarchy_threshold=args.hierarchy_threshold,
        separation=separation,
        separation_threshold=args.separation_threshold,
        detail=detail,
        color_grade=color_grade,
        supersample=supersample,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ffmpeg = args.ffmpeg or find_ffmpeg()
    chafa = args.chafa or find_chafa()
    if args.tools:
        print(f"ffmpeg: {ffmpeg or 'not found'}")
        print(f"chafa: {chafa or 'not found'}")
        print(f"ascii-image-converter: {find_ascii_image_converter() or 'not found'}")
        return 0

    if not args.input:
        print("error: input file is required (or use --tools to list detected tools)", file=sys.stderr)
        return 2

    options = build_options(args)
    formats = [item.strip() for item in args.formats.split(",")]

    try:
        animation = convert_file(args.input, options, ffmpeg_path=ffmpeg)
        outputs = export_many(
            animation,
            args.output_dir,
            formats,
            color=options.color,
            ffmpeg_path=ffmpeg,
            chafa_path=chafa,
        )
    except (ConversionError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Converted {Path(args.input).name}: {len(animation.frames)} frame(s)")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
