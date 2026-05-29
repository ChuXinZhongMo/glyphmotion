from __future__ import annotations

import gzip
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_oneclick.core import ConvertOptions, convert_file
from ascii_oneclick.exporters import export_many

FIXTURE = ROOT / "tests" / "fixtures" / "gradient.gif"


def _animation(color: bool = True):
    options = ConvertOptions(columns=40, fps=10, max_frames=4, color=color)
    return convert_file(FIXTURE, options)


def test_html_contains_frames_and_durations() -> None:
    animation = _animation()
    with tempfile.TemporaryDirectory() as out_dir:
        (path,) = export_many(animation, out_dir, ["html"], color=True)
        text = path.read_text(encoding="utf-8")
        assert "const frames =" in text
        assert "const durations =" in text
        # The frames array holds HTML strings (with embedded semicolons), so
        # parse the durations array instead: it is a plain list of ints and its
        # length must match the decoded frame count.
        start = text.index("const durations =") + len("const durations =")
        array_text = text[start : text.index(";", start)].strip()
        durations = json.loads(array_text)
        assert len(durations) == len(animation.frames)


def test_dur_is_gzip_json_with_frames() -> None:
    animation = _animation()
    with tempfile.TemporaryDirectory() as out_dir:
        (path,) = export_many(animation, out_dir, ["dur"], color=True)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        movie = payload["DurMovie"]
        assert movie["frames"], "DUR has no frames"
        assert movie["sizeX"] == animation.columns
        assert movie["sizeY"] == animation.rows
        assert movie["frames"][0]["contents"], "DUR frame has no contents"


def test_asciimation_header() -> None:
    animation = _animation()
    with tempfile.TemporaryDirectory() as out_dir:
        (path,) = export_many(animation, out_dir, ["asciimation"], color=True)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("x:")
        assert lines[1].startswith("y:")
        assert lines[2].startswith("fps:")
        assert lines[3] == "BEGIN"


def test_txt_nonempty() -> None:
    animation = _animation()
    with tempfile.TemporaryDirectory() as out_dir:
        (path,) = export_many(animation, out_dir, ["txt"], color=True)
        assert path.stat().st_size > 0


def test_unknown_format_raises() -> None:
    animation = _animation()
    with tempfile.TemporaryDirectory() as out_dir:
        try:
            export_many(animation, out_dir, ["bogus"], color=True)
        except ValueError:
            return
    raise AssertionError("export_many should raise ValueError for an unknown format")


def test_mono_html_renders() -> None:
    animation = _animation(color=False)
    with tempfile.TemporaryDirectory() as out_dir:
        (path,) = export_many(animation, out_dir, ["html"], color=False)
        assert path.stat().st_size > 0
        assert "const frames =" in path.read_text(encoding="utf-8")


TESTS = [
    test_html_contains_frames_and_durations,
    test_dur_is_gzip_json_with_frames,
    test_asciimation_header,
    test_txt_nonempty,
    test_unknown_format_raises,
    test_mono_html_renders,
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
    print(f"\nall {len(TESTS)} export test(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runner())
