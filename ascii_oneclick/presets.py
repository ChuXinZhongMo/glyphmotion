"""Shared preset definitions used by both the CLI and the GUI.

Before this module the CLI (`cli.py`) and the GUI (`gui.py`) each kept their
own ``if preset == ...`` ladder, which made it easy for the two front-ends to
drift apart. A ``Preset`` now owns the canonical render settings, and both
front-ends read from the same list.

``options_patch`` always contains the ten core fields the CLI and GUI must
agree on. ``recommended_*`` and ``use_adaptive_aspect`` are soft hints that the
GUI applies to its sizing controls; the CLI keeps explicit ``--width`` etc.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from .core import ConvertOptions


# The fields every preset must define and that the CLI/GUI must resolve to the
# same values. Kept explicit so a malformed preset fails loudly in tests.
CORE_PATCH_FIELDS = (
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
    "vibrance",
)


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    description: str
    options_patch: dict[str, Any] = field(default_factory=dict)
    recommended_width: int | None = None
    recommended_max_frames: int | None = None
    use_adaptive_aspect: bool = False


def _patch(
    *,
    charset_name: str,
    render_mode: str,
    color: bool,
    clean: bool,
    detail: bool,
    hierarchy: bool,
    separation: bool,
    edges: bool,
    color_grade: str,
    supersample: int,
    vibrance: float = 0.0,
) -> dict[str, Any]:
    return {
        "charset_name": charset_name,
        "render_mode": render_mode,
        "color": color,
        "clean": clean,
        "detail": detail,
        "hierarchy": hierarchy,
        "separation": separation,
        "edges": edges,
        "color_grade": color_grade,
        "supersample": supersample,
        "vibrance": vibrance,
    }


PRESETS: tuple[Preset, ...] = (
    Preset(
        name="restore",
        label="清晰还原（黑白）",
        description="清晰还原黑白字符，先判断主体是否可读。",
        options_patch=_patch(
            charset_name="restore",
            render_mode="ascii",
            color=False,
            clean=True,
            detail=True,
            hierarchy=True,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=1,
        ),
    ),
    Preset(
        name="shader-mono",
        label="游戏着色器（黑白）",
        description="游戏后处理风格黑白字符。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="ascii",
            color=False,
            clean=True,
            detail=True,
            hierarchy=False,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=1,
        ),
    ),
    Preset(
        name="shader-color",
        label="游戏着色器（原色彩色）",
        description="游戏后处理风格，使用源色和彩色字符。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="ascii",
            color=True,
            clean=True,
            detail=True,
            hierarchy=False,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=1,
        ),
    ),
    Preset(
        name="shader-color-hd",
        label="游戏着色器（原色高清）",
        description="高清 shader 风格，2x 超采样，速度更慢。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="ascii",
            color=True,
            clean=True,
            detail=True,
            hierarchy=False,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=2,
        ),
        recommended_width=220,
        recommended_max_frames=240,
    ),
    Preset(
        name="adaptive-mono",
        label="自适应混合字符（黑白）",
        description="自适应混合字符黑白版，按区域混合字符细节。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="adaptive",
            color=False,
            clean=True,
            detail=True,
            hierarchy=True,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=2,
        ),
        recommended_width=180,
        use_adaptive_aspect=True,
    ),
    Preset(
        name="adaptive-color",
        label="自适应混合字符（原色彩色）",
        description="自适应混合字符，按局部区域混合普通字符、shader 字符和少量盲文细节。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="adaptive",
            color=True,
            clean=True,
            detail=True,
            hierarchy=True,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=2,
        ),
        recommended_width=220,
        use_adaptive_aspect=True,
    ),
    Preset(
        name="adaptive-vivid",
        label="自适应混合字符（原色鲜艳）",
        description="保留自适应布局和源素材色相，轻微增强已有饱和度与主体亮度。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="adaptive",
            color=True,
            clean=True,
            detail=True,
            hierarchy=True,
            separation=False,
            edges=False,
            color_grade="vivid",
            supersample=2,
        ),
        recommended_width=220,
        use_adaptive_aspect=True,
    ),
    Preset(
        name="adaptive-wide",
        label="自适应混合字符（全彩忠实）",
        description="与原色鲜艳渲染参数相同，不做任何额外色彩增强，颜色完全忠实于素材原色。建议搭配 WebM 全彩格式导出——WebM 使用 yuv444 无色度子采样，GIF/WebM 颜色完全一致；MP4 因 yuv420 色度子采样会损失约 1/3 饱和度。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="adaptive",
            color=True,
            clean=True,
            detail=True,
            hierarchy=True,
            separation=False,
            edges=False,
            color_grade="vivid",
            supersample=2,
            vibrance=0.0,
        ),
        recommended_width=220,
        use_adaptive_aspect=True,
    ),
    Preset(
        name="braille-mono",
        label="盲文高精度（黑白）",
        description="盲文点阵高精度黑白字符，细节多但偏点阵画。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="braille",
            color=False,
            clean=True,
            detail=True,
            hierarchy=False,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=1,
        ),
        recommended_width=160,
    ),
    Preset(
        name="braille-color",
        label="盲文高精度（彩色）",
        description="盲文点阵高精度彩色字符，细节多但偏点阵画。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="braille",
            color=True,
            clean=True,
            detail=True,
            hierarchy=False,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=1,
        ),
        recommended_width=160,
    ),
    Preset(
        name="shader-warm",
        label="游戏着色器（暖色彩色）",
        description="游戏着色器暖色调彩色字符。",
        options_patch=_patch(
            charset_name="shader",
            render_mode="ascii",
            color=True,
            clean=True,
            detail=True,
            hierarchy=False,
            separation=False,
            edges=False,
            color_grade="warm",
            supersample=1,
        ),
    ),
    Preset(
        name="soft",
        label="文字游戏柔和（黑白）",
        description="文字游戏柔和黑白风格。",
        options_patch=_patch(
            charset_name="soft",
            render_mode="ascii",
            color=False,
            clean=True,
            detail=False,
            hierarchy=True,
            separation=False,
            edges=False,
            color_grade="source",
            supersample=1,
        ),
    ),
)

PRESETS_BY_NAME: dict[str, Preset] = {preset.name: preset for preset in PRESETS}

# Canonical hyphenated preset names, for argparse choices.
PRESET_NAMES: list[str] = [preset.name for preset in PRESETS]


def get_preset(name: str) -> Preset:
    try:
        return PRESETS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"Unknown preset: {name}") from exc


def apply_preset(base: ConvertOptions, name: str) -> ConvertOptions:
    """Return ``base`` with the named preset's core render fields applied."""
    preset = get_preset(name)
    return dataclasses.replace(base, **preset.options_patch)
