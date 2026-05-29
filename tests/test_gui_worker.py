from __future__ import annotations

import dataclasses
import inspect
import queue
import sys
import tempfile
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_oneclick.core import ConvertOptions
from ascii_oneclick.gui import (
    ConversionCancelled,
    ConversionFailure,
    ConversionProgress,
    ConversionRequest,
    ConversionSuccess,
    GlyphMotionApp,
)

FIXTURE = ROOT / "tests" / "fixtures" / "gradient.gif"


def _request(input_path: str, output_dir: str) -> ConversionRequest:
    return ConversionRequest(
        input_path=input_path,
        output_dir=output_dir,
        formats=("txt", "png"),
        options=ConvertOptions(columns=32, fps=10, max_frames=3, color=True),
        color=True,
        ffmpeg_path=None,
        chafa_path=None,
    )


def _fake_app() -> types.SimpleNamespace:
    """A stand-in for the app exposing only what the worker may touch."""
    return types.SimpleNamespace(work_queue=queue.Queue())


def test_request_is_immutable() -> None:
    request = _request("in.gif", "out")
    try:
        request.input_path = "other"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ConversionRequest should be frozen/immutable")


def test_worker_reads_only_the_snapshot() -> None:
    """The worker must not read Tkinter variables: only request.* and the queue."""
    source = inspect.getsource(GlyphMotionApp._convert_worker)
    assert "_var" not in source, "worker still references a Tkinter *_var"
    assert "self.color_grade" not in source
    assert "self.supersample" not in source
    # The only attribute the worker may read off self is the queue.
    self_reads = {
        line.split("self.")[1].split(".")[0].split(")")[0].split(",")[0].strip()
        for line in source.splitlines()
        if "self." in line
    }
    assert self_reads <= {"work_queue"}, f"worker touches unexpected self attrs: {self_reads}"


def _drain(work_queue: queue.Queue) -> list:
    messages = []
    while True:
        try:
            messages.append(work_queue.get_nowait())
        except queue.Empty:
            return messages


def test_worker_success_puts_success_message() -> None:
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    with tempfile.TemporaryDirectory(prefix="glyphmotion-test-") as out_dir:
        fake = _fake_app()
        request = _request(str(FIXTURE), out_dir)
        GlyphMotionApp._convert_worker(fake, request, threading.Event())
        messages = _drain(fake.work_queue)
        success = next((m for m in messages if isinstance(m, ConversionSuccess)), None)
        assert success is not None, f"got {messages!r}"
        assert success.animation.frames
        assert success.preview
        assert all(path.exists() and path.stat().st_size > 0 for path in success.outputs)
        # Progress should have been reported and reached the final stretch.
        fractions = [m.fraction for m in messages if isinstance(m, ConversionProgress) and m.fraction]
        assert fractions and max(fractions) > 0.5, f"weak progress: {fractions!r}"


def test_worker_failure_puts_failure_message() -> None:
    with tempfile.TemporaryDirectory(prefix="glyphmotion-test-") as out_dir:
        fake = _fake_app()
        request = _request(str(ROOT / "does-not-exist.gif"), out_dir)
        GlyphMotionApp._convert_worker(fake, request, threading.Event())
        messages = _drain(fake.work_queue)
        failure = next((m for m in messages if isinstance(m, ConversionFailure)), None)
        assert failure is not None, f"got {messages!r}"
        assert failure.message


def test_worker_cancel_puts_cancelled_message() -> None:
    """A pre-set cancel event stops the render and reports cancellation."""
    assert FIXTURE.exists(), f"missing fixture: {FIXTURE}"
    with tempfile.TemporaryDirectory(prefix="glyphmotion-test-") as out_dir:
        fake = _fake_app()
        request = _request(str(FIXTURE), out_dir)
        cancel_event = threading.Event()
        cancel_event.set()
        GlyphMotionApp._convert_worker(fake, request, cancel_event)
        messages = _drain(fake.work_queue)
        assert any(isinstance(m, ConversionCancelled) for m in messages), f"got {messages!r}"
        assert not any(isinstance(m, ConversionSuccess) for m in messages)
        # Nothing should have been written to disk on cancel.
        assert not list(Path(out_dir).iterdir())


TESTS = [
    test_request_is_immutable,
    test_worker_reads_only_the_snapshot,
    test_worker_success_puts_success_message,
    test_worker_failure_puts_failure_message,
    test_worker_cancel_puts_cancelled_message,
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
    print(f"\nall {len(TESTS)} gui worker test(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runner())
