from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_oneclick.core import ConvertOptions, convert_file
from ascii_oneclick.exporters import export_many

FIXTURE_DIR = ROOT / "tests" / "fixtures"
OUT_DIR = ROOT / "tests" / "out"


def make_fixture() -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / "gradient.gif"
    frames = []
    for index in range(4):
        image = Image.new("RGB", (96, 54), (20 + index * 40, 30, 80))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10 + index * 10, 12, 42 + index * 10, 42), fill=(230, 210, 70))
        draw.text((8, 4), f"F{index + 1}", fill=(255, 255, 255))
        frames.append(image)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=80, loop=0)
    return path


def main() -> int:
    source = make_fixture()
    options = ConvertOptions(columns=48, fps=10, max_frames=20, color=True)
    animation = convert_file(source, options)
    outputs = export_many(
        animation,
        OUT_DIR,
        ["txt", "html", "gif", "png", "dur", "asciimation"],
        color=True,
    )
    assert animation.frames
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs)

    dur_path = OUT_DIR / "gradient.dur"
    with gzip.open(dur_path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["DurMovie"]["frames"]
    print("smoke ok")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
