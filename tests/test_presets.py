from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_oneclick.core import ConvertOptions
from ascii_oneclick.formats import (
    DEFAULT_FORMAT_NAMES,
    DEFAULT_FORMATS_CLI,
    FORMATS_BY_NAME,
    OUTPUT_FORMATS,
)
from ascii_oneclick.presets import (
    CORE_PATCH_FIELDS,
    PRESETS,
    PRESETS_BY_NAME,
    apply_preset,
)

# The fields the CLI and GUI must resolve identically for a given preset.
SHARED_FIELDS = (
    "charset_name",
    "render_mode",
    "color",
    "clean",
    "detail",
    "hierarchy",
    "separation",
    "edges",
    "color_grade",
    "supersample",
)


def test_every_preset_patch_has_exactly_core_fields() -> None:
    for preset in PRESETS:
        keys = set(preset.options_patch)
        assert keys == set(CORE_PATCH_FIELDS), f"{preset.name} patch keys = {sorted(keys)}"


def test_apply_preset_sets_shared_fields_from_patch() -> None:
    """apply_preset() is the single source the CLI uses; the GUI reads the same
    options_patch. This proves the shared fields match the declared patch."""
    base = ConvertOptions()
    for preset in PRESETS:
        resolved = apply_preset(base, preset.name)
        for field_name in SHARED_FIELDS:
            assert getattr(resolved, field_name) == preset.options_patch[field_name], (
                f"{preset.name}.{field_name}: "
                f"{getattr(resolved, field_name)!r} != {preset.options_patch[field_name]!r}"
            )


def test_apply_preset_keeps_non_patch_fields() -> None:
    """Size/fps/thresholds are not owned by presets and must survive."""
    base = ConvertOptions(columns=321, fps=7.0, max_frames=99, edge_threshold=12)
    resolved = apply_preset(base, "shader-color")
    assert resolved.columns == 321
    assert resolved.fps == 7.0
    assert resolved.max_frames == 99
    assert resolved.edge_threshold == 12


def test_preset_spot_checks() -> None:
    restore = apply_preset(ConvertOptions(), "restore")
    assert (restore.charset_name, restore.render_mode, restore.color) == ("restore", "ascii", False)

    vivid = apply_preset(ConvertOptions(), "adaptive-vivid")
    assert (vivid.render_mode, vivid.color_grade, vivid.supersample) == ("adaptive", "vivid", 2)

    warm = apply_preset(ConvertOptions(), "shader-warm")
    assert warm.color_grade == "warm"


def test_apply_preset_unknown_raises() -> None:
    try:
        apply_preset(ConvertOptions(), "does-not-exist")
    except KeyError:
        return
    raise AssertionError("apply_preset should raise KeyError for unknown preset")


def test_preset_labels_unique() -> None:
    labels = [p.label for p in PRESETS]
    assert len(labels) == len(set(labels)), "preset labels must be unique"
    assert len(PRESETS_BY_NAME) == len(PRESETS), "preset names must be unique"


def test_default_formats_cli_matches_default_names() -> None:
    assert DEFAULT_FORMATS_CLI == ",".join(DEFAULT_FORMAT_NAMES)
    assert DEFAULT_FORMAT_NAMES == ["txt", "html", "gif", "png", "dur", "asciimation"]


def test_format_tool_dependencies() -> None:
    assert FORMATS_BY_NAME["mp4"].requires_tool == "ffmpeg"
    assert FORMATS_BY_NAME["mp4"].tool_optional is False
    assert FORMATS_BY_NAME["ansi"].requires_tool == "chafa"
    assert FORMATS_BY_NAME["ansi"].tool_optional is True
    # Core formats need no external tool.
    for name in ("txt", "html", "gif", "png", "dur", "asciimation"):
        assert FORMATS_BY_NAME[name].requires_tool is None


def test_all_formats_have_labels() -> None:
    for fmt in OUTPUT_FORMATS:
        assert fmt.label and isinstance(fmt.label, str)


TESTS = [
    test_every_preset_patch_has_exactly_core_fields,
    test_apply_preset_sets_shared_fields_from_patch,
    test_apply_preset_keeps_non_patch_fields,
    test_preset_spot_checks,
    test_apply_preset_unknown_raises,
    test_preset_labels_unique,
    test_default_formats_cli_matches_default_names,
    test_format_tool_dependencies,
    test_all_formats_have_labels,
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
    print(f"\nall {len(TESTS)} preset/format test(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_runner())
