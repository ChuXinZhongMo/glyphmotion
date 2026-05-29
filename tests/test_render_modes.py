from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_oneclick.core import ConvertOptions, convert_file
from ascii_oneclick.exporters import is_braille_frame

FIXTURE = ROOT / "tests" / "fixtures" / "gradient.gif"

MODES = ["ascii", "adaptive", "braille", "fullblock", "halfblock"]


def _convert(mode: str, charset: str = "default", color: bool = True):
    options = ConvertOptions(
        columns=40,
        fps=10,
        max_frames=3,
        render_mode=mode,
        charset_name=charset,
        color=color,
    )
    return convert_file(FIXTURE, options)


def _check_frames_nonempty(animation) -> None:
    assert animation.frames, "no frames produced"
    for frame in animation.frames:
        assert frame.lines, "frame has no lines"
        widths = {len(line) for line in frame.lines}
        assert len(widths) == 1, f"ragged frame widths: {widths}"
        assert widths.pop() > 0, "empty rows"
        assert len(frame.colors) == len(frame.lines)


def test_mode_ascii() -> None:
    _check_frames_nonempty(_convert("ascii"))


def test_mode_adaptive() -> None:
    _check_frames_nonempty(_convert("adaptive", charset="shader"))


def test_mode_braille() -> None:
    animation = _convert("braille", charset="shader")
    _check_frames_nonempty(animation)
    assert any(is_braille_frame(frame) for frame in animation.frames), "no braille glyphs emitted"


def test_mode_fullblock() -> None:
    animation = _convert("fullblock")
    _check_frames_nonempty(animation)
    assert all(set(line) <= {"█"} for line in animation.frames[0].lines), "fullblock not solid blocks"


def test_mode_halfblock() -> None:
    animation = _convert("halfblock")
    _check_frames_nonempty(animation)
    # halfblock encodes two pixels per cell via fg/bg colors.
    assert animation.frames[0].bg_colors is not None, "halfblock should carry bg_colors"
    assert all(set(line) <= {"▀"} for line in animation.frames[0].lines)


def test_shader_charset_routes_through_shader_path() -> None:
    # charset "shader" in ascii mode uses the shader renderer; should be non-empty.
    _check_frames_nonempty(_convert("ascii", charset="shader"))


def test_mono_mode_still_produces_frames() -> None:
    _check_frames_nonempty(_convert("ascii", color=False))


TESTS = [
    test_mode_ascii,
    test_mode_adaptive,
    test_mode_braille,
    test_mode_fullblock,
    test_mode_halfblock,
    test_shader_charset_routes_through_shader_path,
    test_mono_mode_still_produces_frames,
]


def main_runner() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {test.__name__}: {exc!r}")
        else:
            print(f"ok   {test.__name__}")
    if failures:
        print(f"\n{failures} test(s) failed")
        return 1
    print(f"\nall {len(TESTS)} render-mode test(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runner())
