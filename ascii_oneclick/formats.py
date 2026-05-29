"""Shared output-format definitions for the CLI and GUI.

Single source of truth for the export format list, the Chinese UI labels, the
default ("common") selection, and which external tool a format depends on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputFormat:
    name: str
    label: str
    default: bool
    requires_tool: str | None = None
    # When True the tool is only an enhancement and a built-in fallback exists,
    # so the format still works without it (e.g. ANSI without Chafa).
    tool_optional: bool = False


OUTPUT_FORMATS: tuple[OutputFormat, ...] = (
    OutputFormat("txt", "TXT 文本", default=True),
    OutputFormat("html", "HTML 动画网页", default=True),
    OutputFormat("gif", "GIF 动图", default=True),
    OutputFormat("png", "PNG 首帧图片", default=True),
    OutputFormat("mp4", "MP4 视频", default=False, requires_tool="ffmpeg"),
    OutputFormat("dur", "Durdraw 工程 (.dur)", default=True),
    OutputFormat("ansi", "ANSI 终端动画", default=False, requires_tool="chafa", tool_optional=True),
    OutputFormat("asciimation", "Asciimation 文本 (.aam)", default=True),
)

FORMATS_BY_NAME: dict[str, OutputFormat] = {fmt.name: fmt for fmt in OUTPUT_FORMATS}

FORMAT_LABELS: dict[str, str] = {fmt.name: fmt.label for fmt in OUTPUT_FORMATS}

# The common / default selection, shared by CLI default and GUI "常用" button.
DEFAULT_FORMAT_NAMES: list[str] = [fmt.name for fmt in OUTPUT_FORMATS if fmt.default]

# Comma-separated default for the CLI --formats argument.
DEFAULT_FORMATS_CLI: str = ",".join(DEFAULT_FORMAT_NAMES)
