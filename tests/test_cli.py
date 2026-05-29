from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_oneclick.cli import build_options, build_parser, main


def options_for(*argv: str):
    """Parse CLI args and resolve them to ConvertOptions without converting."""
    args = build_parser().parse_args(list(argv))
    return build_options(args)


def test_tools_without_input_returns_zero() -> None:
    """`--tools` must work without an input file (Phase 0 regression)."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(["--tools"])
    assert code == 0, f"--tools should return 0, got {code}"
    output = buffer.getvalue()
    assert "ffmpeg:" in output
    assert "chafa:" in output
    assert "ascii-image-converter:" in output


def test_missing_input_without_tools_fails() -> None:
    """Without --tools an input file is still required, with a clear error."""
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        code = main([])
    assert code != 0, "missing input should return a non-zero exit code"
    assert "input" in buffer.getvalue().lower()


def test_preset_restore() -> None:
    options = options_for("in.gif", "--preset", "restore")
    assert options.charset_name == "restore"
    assert options.render_mode == "ascii"
    assert options.color is False
    assert options.clean is True
    assert options.detail is True
    assert options.hierarchy is True
    assert options.separation is False
    assert options.edges is False
    assert options.color_grade == "source"
    assert options.supersample == 1


def test_preset_shader_color() -> None:
    options = options_for("in.gif", "--preset", "shader-color")
    assert options.charset_name == "shader"
    assert options.render_mode == "ascii"
    assert options.color is True
    assert options.clean is True
    assert options.detail is True
    assert options.hierarchy is False
    assert options.separation is False
    assert options.edges is False
    assert options.color_grade == "source"
    assert options.supersample == 1


def test_preset_adaptive_color() -> None:
    options = options_for("in.gif", "--preset", "adaptive-color")
    assert options.charset_name == "shader"
    assert options.render_mode == "adaptive"
    assert options.color is True
    assert options.hierarchy is True
    assert options.color_grade == "source"
    assert options.supersample == 2


def test_preset_adaptive_vivid() -> None:
    options = options_for("in.gif", "--preset", "adaptive-vivid")
    assert options.render_mode == "adaptive"
    assert options.color is True
    assert options.color_grade == "vivid"
    assert options.supersample == 2


def test_preset_braille_color() -> None:
    options = options_for("in.gif", "--preset", "braille-color")
    assert options.charset_name == "shader"
    assert options.render_mode == "braille"
    assert options.color is True
    assert options.color_grade == "source"


def test_preset_soft() -> None:
    options = options_for("in.gif", "--preset", "soft")
    assert options.charset_name == "soft"
    assert options.render_mode == "ascii"
    assert options.color is False
    assert options.detail is False
    assert options.hierarchy is True


def test_shader_color_shortcut_matches_preset() -> None:
    """--shader-color is documented as a shortcut for --preset shader-color."""
    shortcut = options_for("in.gif", "--shader-color")
    preset = options_for("in.gif", "--preset", "shader-color")
    assert shortcut == preset


def test_mono_flag_disables_color() -> None:
    options = options_for("in.gif", "--mono")
    assert options.color is False


TESTS = [
    test_tools_without_input_returns_zero,
    test_missing_input_without_tools_fails,
    test_preset_restore,
    test_preset_shader_color,
    test_preset_adaptive_color,
    test_preset_adaptive_vivid,
    test_preset_braille_color,
    test_preset_soft,
    test_shader_color_shortcut_matches_preset,
    test_mono_flag_disables_color,
]


def main_runner() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors
            failures += 1
            print(f"ERROR {test.__name__}: {exc!r}")
        else:
            print(f"ok   {test.__name__}")
    if failures:
        print(f"\n{failures} test(s) failed")
        return 1
    print(f"\nall {len(TESTS)} cli test(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runner())
