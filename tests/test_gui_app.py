from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tkinter as tk

from ascii_oneclick.core import AsciiAnimation, AsciiFrame
from ascii_oneclick.gui import (
    PRESET_LABEL_BY_NAME,
    RENDER_MODE_LABELS,
    ConversionSuccess,
    GlyphMotionApp,
)


class DisplayUnavailable(Exception):
    pass


def _make_app() -> GlyphMotionApp:
    try:
        app = GlyphMotionApp()
    except tk.TclError as exc:  # no display (headless CI)
        raise DisplayUnavailable(str(exc)) from exc
    app.update_idletasks()
    return app


def _sample_success(out_dir: str) -> ConversionSuccess:
    frame = AsciiFrame(lines=["abc"], colors=[[(1, 1, 1)] * 3], duration=0.1)
    animation = AsciiAnimation(frames=[frame], columns=3, rows=1, fps=10, source=Path("demo.gif"))
    outputs = [Path(out_dir) / "demo.txt", Path(out_dir) / "demo.html"]
    for path in outputs:
        path.write_text("x", encoding="utf-8")
    return ConversionSuccess(animation=animation, outputs=outputs, preview="abc")


# ---- Tk-dependent tests (skip cleanly without a display) -------------------

def test_app_builds_and_destroys() -> None:
    app = _make_app()
    try:
        assert app.winfo_class() == "Tk"
    finally:
        app.destroy()


def test_preset_change_updates_controls() -> None:
    app = _make_app()
    try:
        app.preset_var.set(PRESET_LABEL_BY_NAME["adaptive-vivid"])
        app.update_idletasks()
        assert app.render_mode_var.get() == RENDER_MODE_LABELS["adaptive"]
        assert app.color_var.get() is True
        assert app.color_grade == "vivid"
        assert app.supersample == 2
    finally:
        app.destroy()


def test_success_populates_output_list_and_restores_button() -> None:
    app = _make_app()
    try:
        with tempfile.TemporaryDirectory() as out_dir:
            app._conversion_running = True
            app.convert_button.configure(state=tk.DISABLED)
            app.work_queue.put(_sample_success(out_dir))
            app._poll_queue()
            assert app.output_list.size() == 2
            assert str(app.open_dir_button["state"]) == "normal"
            assert str(app.open_file_button["state"]) == "normal"
            assert app._conversion_running is False
            assert str(app.convert_button["state"]) == "normal"
            assert app.last_output_dir == Path(out_dir)
    finally:
        app.destroy()


def test_preview_random_and_stepping() -> None:
    app = _make_app()
    try:
        frames = [
            AsciiFrame(
                lines=["ab", "cd"],
                colors=[[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (255, 255, 0)]],
                duration=0.05,
            )
            for _ in range(3)
        ]
        anim = AsciiAnimation(frames=frames, columns=2, rows=2, fps=10, source=Path("x.gif"))
        app._set_preview_animation(anim)
        # A frame is shown and nav controls are enabled for a multi-frame clip.
        assert app.preview_meta_var.get() in {f"帧 {i} / 3" for i in (1, 2, 3)}
        assert str(app.random_button["state"]) == "normal"
        assert "ab" in app.preview.get("1.0", "end-1c")
        # Stepping wraps within range.
        app._preview_index = 0
        app._preview_next()
        assert app._preview_index == 1
        assert app.preview_meta_var.get() == "帧 2 / 3"
        app._preview_prev()
        assert app._preview_index == 0
        # Random jumps to a different in-range frame and never raises.
        app._preview_random()
        assert app._preview_index != 0
        assert 0 <= app._preview_index < 3
        # Zoom must not raise.
        app._zoom_preview(1)
        app._zoom_preview(-1)
    finally:
        app.destroy()


def test_preview_single_frame_disables_nav() -> None:
    app = _make_app()
    try:
        frame = AsciiFrame(lines=["xy"], colors=[[(10, 20, 30), (40, 50, 60)]], duration=0.1)
        anim = AsciiAnimation(frames=[frame], columns=2, rows=1, fps=10, source=Path("x.gif"))
        app._set_preview_animation(anim)
        assert app.preview_meta_var.get() == "帧 1 / 1"
        assert str(app.random_button["state"]) == "disabled"
        # Random on a single frame is a no-op, not an error.
        app._preview_random()
        assert app._preview_index == 0
    finally:
        app.destroy()


# ---- Pure-logic test (no display needed) -----------------------------------

def test_format_checkbox_label_tool_hints() -> None:
    label = GlyphMotionApp._format_checkbox_label
    assert label("txt", {"ffmpeg": True, "chafa": True}) == "TXT 文本"
    assert "需 FFmpeg" in label("mp4", {"ffmpeg": True, "chafa": False})
    assert "未检测到" in label("mp4", {"ffmpeg": False, "chafa": False})
    ansi_ok = label("ansi", {"ffmpeg": True, "chafa": True})
    assert "建议 Chafa" in ansi_ok
    ansi_missing = label("ansi", {"ffmpeg": True, "chafa": False})
    assert "降级" in ansi_missing


TK_TESTS = [
    test_app_builds_and_destroys,
    test_preset_change_updates_controls,
    test_success_populates_output_list_and_restores_button,
    test_preview_random_and_stepping,
    test_preview_single_frame_disables_nav,
]
LOGIC_TESTS = [
    test_format_checkbox_label_tool_hints,
]


def main_runner() -> int:
    failures = 0
    skipped = 0
    for test in TK_TESTS + LOGIC_TESTS:
        try:
            test()
        except DisplayUnavailable:
            skipped += 1
            print(f"skip {test.__name__}: no display")
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
    note = f" ({skipped} skipped, no display)" if skipped else ""
    print(f"\nall gui app test(s) passed{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runner())
